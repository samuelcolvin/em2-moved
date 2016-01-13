"""
Main interface to em2
"""
import logging
import datetime

import pytz

from .exceptions import (InsufficientPermissions, ComponentNotFound, VerbNotFound, ComponentNotLocked,
                         ComponentLocked, Em2TypeError)
from .utils import get_options, random_name
from .data_store import DataStore
from .send import BasePropagator

logger = logging.getLogger('em2')


class Verbs:
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'
    UNLOCK = 'unlock'
    # is there anywhere we need this apparent from actually publishing conversations?
    # seems ugly to have a verb for one use. let's wait and see
    PUBLISH = 'publish'


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
    CONVERSATIONS = 'conversations'


class Action:
    def __init__(self, actor, conversation, verb, component, item=None, timestamp=None, remote=False):
        self.actor_addr = actor
        self.actor_id = None
        self.perm = None
        self.con = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.remote = remote

    async def set_actor(self, ds):
        self.actor_id, self.perm = await ds.get_participant(self.con, self.actor_addr)

    def __repr__(self):
        attrs = ['actor_addr', 'actor_id', 'perm', 'con', 'verb', 'component', 'item', 'timestamp', 'remote']
        return '<Action({})>'.format(', '.join('{}={}'.format(a, getattr(self, a)) for a in attrs))


class Controller:
    """
    Top level class for accessing conversations and conversation components.
    """
    def __init__(self, data_store, propagator, timezone_name='utc', ref=None):
        assert isinstance(data_store, DataStore)
        assert isinstance(propagator, BasePropagator)
        self.ds = data_store
        self.prop = propagator
        self.timezone_name = timezone_name
        self.ref = ref if ref is not None else random_name()
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
        if action.component == Components.CONVERSATIONS:
            component_cls = self.conversations
        else:
            component_cls = self.components.get(action.component)

        if component_cls is None:
            raise ComponentNotFound('{} is not a valid component'.format(action.component))

        if action.verb not in self.valid_verbs:
            raise VerbNotFound('{} is not a valid verb, verbs: {}'.format(action.verb, self.valid_verbs))

        func = getattr(component_cls, action.verb, None)
        if func is None:
            raise VerbNotFound('{} is not an available verb on {}'.format(action.verb, action.component))

        # FIXME this is ugly and there are probably more cases where we don't want to do this
        if not (action.component == Components.CONVERSATIONS and action.verb == Verbs.ADD):
            await action.set_actor(self.ds)
        try:
            return await func(action, **kwargs)
        except TypeError as e:
            raise Em2TypeError(str(e))

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    def _subdict(self, data, first_chars):
        return {k[2:]: v for k, v in data.items() if k[0] in first_chars}

    async def event(self, action, timestamp=None, **data):
        """
        Record and propagate updates of conversations and conversation components.

        :param action: Action instance
        :param timestamp: datetime the update occurred, if None this is set to now
        :param data: extra information to either be saved (s_*), propagated (p_*) or both (b_*)
        """
        timestamp = timestamp or self.now_tz()
        logger.debug('event on %d: author: "%s", action: "%s", component: %s %s',
                     action.con, action.actor_addr, action.verb, action.component, action.item)
        save_data = self._subdict(data, 'sb')
        await self.ds.save_event(action, save_data, timestamp)
        if action.remote:
            return
        status = await self.ds.get_status(action.con)
        if status == Conversations.Status.DRAFT:
            return
        propagate_data = self._subdict(data, 'pb')
        await self.prop.propagate(action, propagate_data, timestamp)

    def __repr__(self):
        return '<Controller({})>'.format(self.ref)


class Conversations:
    name = Components.CONVERSATIONS
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
        # TODO this needs refactoring to work with add
        timestamp = self.controller.now_tz()
        con_id = self.ds.hash(creator, timestamp.isoformat(), subject, method='sha256')
        await self.ds.create_conversation(
            con_id=con_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.DRAFT,
        )
        logger.info('created conversation: %s..., creator: "%s", subject: "%s"', con_id[:6], creator, subject)

        participants = self.controller.components[Components.PARTICIPANTS]
        await participants.add_first(con_id, creator)

        if body is not None:
            messages = self.controller.components[Components.MESSAGES]
            a = Action(creator, con_id, Verbs.ADD, Components.MESSAGES)
            await a.set_actor(self.ds)
            await messages.add_basic(a, body=body)
        return con_id

    async def add(self, action, subject, body):
        """
        Add a new conversation created on another platform.
        """
        creator = action.actor_addr
        timestamp = action.timestamp
        con_id = self.ds.hash(creator, timestamp.isoformat(), subject, method='sha256')
        con_id = await self.ds.create_conversation(
            con_id=con_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.PENDING,
        )
        logger.info('created external conversation: %s..., creator: "%s", subject: "%s"', con_id[:6], creator, subject)

        participants_component = self.controller.components[Components.PARTICIPANTS]
        await participants_component.add_first(con_id, creator)

        messages_component = self.controller.components[Components.MESSAGES]
        a = Action(creator, con_id, Verbs.ADD, Components.MESSAGES)
        await a.set_actor(self.ds)
        await messages_component.add_basic(a, body=body)

    async def publish(self, action):
        # TODO this needs refactoring to work with more initial content
        await self.ds.set_status(action.con, self.Status.ACTIVE)

        subject = await self.ds.get_subject(action.con)
        timestamp = self.controller.now_tz()

        new_con_id = self.ds.hash(action.actor_addr, timestamp.isoformat(), subject, method='sha256')
        await self.ds.update_conversation_id(action.con, new_con_id)

        new_action = Action(action.actor_addr, new_con_id, Verbs.ADD, Components.CONVERSATIONS)
        first_message = await self.ds.get_first_message(new_con_id)
        body = first_message['body']
        await self.controller.event(new_action, timestamp=timestamp, p_subject=subject, p_body=body)

    async def get_by_id(self, id):
        raise NotImplementedError()

    def __repr__(self):
        return '<Conversations on {}>'.format(self.controller)


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

    async def add(self, action, body, parent_id):
        await self.ds.get_message_author(action.con, parent_id)
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE access required to add messages')
        action.item = await self.add_basic(action, body, parent_id)
        await self._event(action, p_parent_id=parent_id, p_body=body)

    async def edit(self, action, body):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self._edit(action.con, action.item, body=body)
        await self._event(action, b_value=body)

    async def delta_edit(self, action, body):
        raise NotImplementedError()

    async def delete(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self._delete(action.con, action.item)
        await self._event(action)

    async def lock(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await self.ds.lock_component(self.name, action.con, action.item)
        await self._event(action)

    async def unlock(self, action):
        await self._check_permissions(action)
        if not await self.ds.get_message_locked(self.name, action.con, action.item):
            raise ComponentNotLocked('{} with id = {} not locked'.format(self.name, action.item))
        await self.ds.unlock_component(self.name, action.con, action.item)
        await self._event(action)

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
        # TODO check the address is valid
        new_participant_id = await self._add(
            action.con,
            email=email,
            permissions=permissions,
        )
        logger.info('added participant to %d: email: "%s", permissions: "%s"', action.con, email, permissions)
        await self.controller.prop.add_participant(action, email)
        await self._event(action, new_participant_id)
        return new_participant_id

# shortcut
perms = Participants.Permissions
