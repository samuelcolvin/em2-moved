"""
Main interface to em2
"""
import logging
import datetime

import pytz

from .exceptions import InsufficientPermissions, ComponentNotFound, VerbNotFound, ComponentNotLocked, ComponentLocked
from .utils import get_options

logger = logging.getLogger('em2')


class Verbs:
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'
    UNLOCK = 'unlock'


class Components:
    MESSAGES = 'messages'
    COMMENTS = 'comments'
    PARTICIPANTS = 'participants'
    LABELS = 'labels'
    SUBJECT = 'subject'
    EXPIRY = 'expiry'
    ATTACHMENTS = 'attachments'
    EXTRAS = 'extras'
    RESPONSES = 'responses'


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
    """
    Top level class for accessing conversations and conversation components.
    """
    def __init__(self, data_store, event_handler=None, timezone_name='utc'):
        self.ds = data_store
        self.event_handler = event_handler
        self.timezone_name = timezone_name
        self.conversations = Conversations(self)
        components = [Messages, Participants]
        self.components = {c.name: c(self) for c in components}
        self.valid_verbs = set(get_options(Verbs))

    async def act(self, action, **kwargs):
        """
        Routes actions to the appropriate component and executes the right verb.
        :param action: action instance
        :param kwargs: extra key word arguments to pass to the method with action
        :return: result of method associated with verb
        """
        assert isinstance(action, Action)
        await action.set_actor(self.ds)
        component_cls = self.components.get(action.component)
        if component_cls is None:
            raise ComponentNotFound('{} is not a valid component'.format(action.component))

        if action.verb not in self.valid_verbs:
            raise VerbNotFound('{} is not a valid verb, verbs: {}'.format(action.verb, self.valid_verbs))
        func = getattr(component_cls, action.verb, None)
        if func is None:
            raise VerbNotFound('{} is not an available verb on {}'.format(action.verb, action.component))
        return await func(action, **kwargs)

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    async def event(self, action, component_id, timestamp=None, **data):
        """
        Record and propagate updates of conversations and conversation components.

        Events are always recorded but can be cleared before publish.

        :param action: Action instance
        :param component_id: id of item created or modified
        :param timestamp: datetime the update occurred, if None this is set to now
        :param data: extra information associated with the update
        :return: None
        """
        timestamp = timestamp or self.now_tz()
        logger.debug('change occurred on %d: author: "%s", action: "%s", component: %s %s',
                     action.con, action.actor_addr, action.verb, action.component, component_id)
        await self.ds.save_event(action, component_id, data, timestamp)
        if self.event_handler:
            await self.event_handler(action, component_id, data, timestamp)


class Conversations:
    name = 'conversations'
    event = None

    def __init__(self, controller):
        self.controller = controller
        self.ds = self.controller.ds

    class Status:
        DRAFT = 'draft'
        PENDING = 'pending'
        ACTIVE = 'active'
        EXPIRED = 'expired'
        DELETED = 'deleted'

    async def create(self, creator, subject, body=None):
        timestamp = self.controller.now_tz()
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

        participants = self.controller.components[Components.PARTICIPANTS]
        await participants.add_first(con_id, creator)

        if body is not None:
            messages = self.controller.components[Components.MESSAGES]
            a = Action(creator, con_id, Verbs.ADD, Components.MESSAGES)
            await a.set_actor(self.ds)
            await messages.add_basic(a, body=body)
        return con_id

    async def publish(self):
        raise NotImplemented

    async def get_by_global_id(self, id):
        raise NotImplemented


class _Component:
    name = None

    def __init__(self, controller):
        self.controller = controller
        self.ds = self.controller.ds

    async def _event(self, *args, **kwargs):
        return await self.controller.event(*args, **kwargs)

    async def _add(self, conversation, **kwargs):
        return await self.ds.add_component(self.name, conversation, **kwargs)

    async def _edit(self, conversation, id, **kwargs):
        return await self.ds.edit_component(self.name, conversation, id, **kwargs)

    async def _delete(self, conversation, id):
        return await self.ds.delete_component(self.name, conversation, id)


class Messages(_Component):
    name = Components.MESSAGES

    async def add_basic(self, action, body, parent_id=None):
        timestamp = self.controller.now_tz()
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
        await self._event(action, id)

    async def edit(self, action, body):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self._edit(action.con, action.item, body=body)
        await self._event(action, action.item, value=body)

    async def delta_edit(self, action, body):
        raise NotImplementedError()

    async def delete(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self._delete(action.con, action.item)
        await self._event(action, action.item)

    async def lock(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self.ds.lock_component(self.name, action.con, action.item)
        await self._event(action, action.item)

    async def unlock(self, action):
        await self._check_permissions(action)
        if not await self.ds.get_message_locked(self.name, action.con, action.item):
            raise ComponentNotLocked('{} with id = {} not locked'.format(self.name, action.item))
        await self.ds.unlock_component(self.name, action.con, action.item)
        await self._event(action, action.item)

    async def _check_permissions(self, action):
        if action.perm == perms.WRITE:
            author_pid = await self.ds.get_message_author(action.con, action.item)
            if author_pid != action.actor_id:
                raise InsufficientPermissions('To {} a message authored by another participant '
                                              'FULL permissions are requires'.format(action.verb))
        elif action.perm != perms.FULL:
            raise InsufficientPermissions('To {} a message requires FULL or WRITE permissions'.format(action.verb))

    async def _check_locked(self, action):
        if await self.ds.get_message_locked(self.name, action.con, action.item):
            raise ComponentLocked('{} with id = {} locked'.format(self.name, action.item))


class Participants(_Component):
    name = Components.PARTICIPANTS

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
            raise InsufficientPermissions('FULL permission are required to add participants with FULL permissions')
        new_participant_id = await self._add(
            action.con,
            email=email,
            permissions=permissions,
        )
        logger.info('added participant to %d: email: "%s", permissions: "%s"', action.con, email, permissions)
        await self._event(action, new_participant_id)
        return new_participant_id

# shortcut
perms = Participants.Permissions
