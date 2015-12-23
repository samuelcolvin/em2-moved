"""
Synchronous interface to em2
"""
import logging

from .exceptions import InsufficientPermissions, ComponentNotFound, VerbNotFound
from .model_extras import get_options

logger = logging.getLogger('em2')


class Verbs:
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'
    UNLOCK = 'unlock'


class Components:
    MESSAGE = 'messages'
    COMMENT = 'comments'
    PARTICIPANT = 'participants'
    LABEL = 'labels'
    SUBJECT = 'subjects'
    EXPIRY = 'expiry'
    ATTACHMENT = 'attachments'
    EXTRA = 'extras'
    RESPONSE = 'responses'


class Action:
    def __init__(self, actor, conversation, verb, component, item=None):
        self.actor_addr = actor
        self.actor_id = None
        self.perm = None
        self.con = conversation
        self.verb = verb
        self.component = component
        self.item = item

    async def set_actor(self, ds):
        # TODO it may be possible to provide functionality to cache these results to reduce queries
        self.actor_id, self.perm = await ds.get_participant(self.con, self.actor_addr)


class Controller:
    def __init__(self, data_store):
        self.ds = data_store
        self.conversations = Conversations(self)
        components = [Messages, Participants]
        self.components = {c.name: c(self) for c in components}
        self.valid_verbs = set(get_options(Verbs))

    async def act(self, action, **kwargs):
        assert isinstance(action, Action)
        await action.set_actor(self.ds)
        component_cls = self.components.get(action.component)
        if component_cls is None:
            raise ComponentNotFound('{} is not a valid component'.format(action.component))

        assert action.verb in self.valid_verbs, '{} not in verbs: {}'.format(action.verb, self.valid_verbs)
        func = getattr(component_cls, action.verb, None)
        if func is None:
            raise VerbNotFound('{} is not an available verb on {}'.format(action.verb, action.component))
        return await func(action, **kwargs)


class Conversations:
    name = 'conversations'
    event = None

    def __init__(self, controller):
        self.ctrl = controller
        self.ds = self.ctrl.ds

    class Status:
        DRAFT = 'draft'
        PENDING = 'pending'
        ACTIVE = 'active'
        EXPIRED = 'expired'
        DELETED = 'deleted'

    async def create(self, creator, subject, body=None):
        timestamp = self.ds.now_tz()
        global_id = self.ds.hash(creator, timestamp.isoformat(), subject, method='sha256')
        con_id = await self.ds.create_conversation(
            global_id=global_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.DRAFT,
        )
        logger.info('created conversation: %s..., id: %d, creator: "%s", subject: "%s"',
                    global_id[:6], con_id, creator, subject)

        participants = self.ctrl.components[Components.PARTICIPANT]
        await participants.add_first(con_id, creator)

        if body is not None:
            messages = self.ctrl.components[Components.MESSAGE]
            a = Action(creator, con_id, Verbs.ADD, Components.MESSAGE)
            await a.set_actor(self.ds)
            await messages.add_basic(a, body=body)
        return con_id

    async def publish(self):
        raise NotImplemented

    async def get_by_global_id(self, id):
        raise NotImplemented


class _Components:
    name = None

    def __init__(self, controller):
        self.controller = controller
        self.ds = self.controller.ds

    async def _add(self, conversation, **kwargs):
        return await self.ds.add_component(self.name, conversation, **kwargs)

    async def _edit(self, conversation, id, **kwargs):
        return await self.ds.edit_component(self.name, conversation, id, **kwargs)


class Messages(_Components):
    name = 'messages'

    async def add_basic(self, action, body, parent_id=None):
        timestamp = self.ds.now_tz()
        id = self.ds.hash(action.actor_addr, timestamp.isoformat(), body, parent_id)
        await self._add(
            action.con,
            id=id,
            author=action.actor_id,
            timestamp=timestamp,
            body=body,
            parent=parent_id,
        )
        return id

    async def add(self, action, parent_id, body):
        await self.ds.get_message_author(action.con, parent_id)
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE access required to add messages')
        id = await self.add_basic(action, body, parent_id)
        await self.ds.event(action, id)

    async def edit(self, action, id, body):
        if action.perm == perms.WRITE:
            author_pid = await self.ds.get_message_author(action.con, id)
            if author_pid == action.actor_id:
                raise InsufficientPermissions('Editing a message authored by another participant '
                                              'requires FULL permissions')
        elif action.perm != perms.FULL:
            raise InsufficientPermissions('Editing a message requires FULL or WRITE permissions')
        await self._edit(
            action.con,
            id,
            body=body,
        )
        await self.ds.event(action, id, value=body)

    async def delta_edit(self, action, id, body):
        raise NotImplementedError()

    async def delete(self, action, id):
        raise NotImplementedError()

    async def lock(self, action, id):
        raise NotImplementedError()

    async def unlock(self, action, id):
        raise NotImplementedError()


class Participants(_Components):
    name = 'participants'

    class Permissions:
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    async def add_first(self, con, email):
        new_participant_id = await self._add(
            con,
            email=email,
            permissions=perms.FULL,
        )
        logger.info('first participant added to %d: email: "%s"', con, email)
        return new_participant_id

    async def add(self, action, email, permissions):
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE permission are required to add participants')
        if action.perm == perms.WRITE and permissions == perms.FULL:
            raise InsufficientPermissions('FULL permission are required to add participants with FULL permissions.')
        new_participant_id = await self._add(
            action.con,
            email=email,
            permissions=permissions,
        )
        logger.info('added participant to %d: email: "%s", permissions: "%s"', action.con, email, permissions)
        await self.ds.event(action, new_participant_id)
        return new_participant_id

# shortcut
perms = Participants.Permissions
