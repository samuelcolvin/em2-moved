"""
Main interface to em2
"""
import logging
import datetime
import hashlib
import inspect

import pytz
from cerberus import Validator

from .exceptions import (InsufficientPermissions, ComponentNotFound, VerbNotFound, ComponentNotLocked,
                         ComponentLocked, BadDataException, BadHash, MisshapedDataException)
from .utils import get_options, random_name
from .data_store import DataStore
from .send import BasePropagator
from .common import Components

logger = logging.getLogger('em2')


class Verbs:
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'
    UNLOCK = 'unlock'
    # is there anywhere we need this apart from actually publishing conversations?
    # seems ugly to have a verb for one use
    PUBLISH = 'publish'


class Action:
    def __init__(self, actor, conversation, verb, component, item=None, timestamp=None, remote=False):
        self.ds = None
        self.actor_id = None
        self.perm = None
        self.actor_addr = actor
        self.con = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.remote = remote

    async def prepare(self, ds):
        self.ds = ds.new_con_ds(self.con)
        self.actor_id, self.perm = await self.ds.get_participant(self.actor_addr)

    def __repr__(self):
        attrs = ['actor_addr', 'actor_id', 'perm', 'con', 'verb', 'component', 'item', 'timestamp', 'remote']
        return '<Action({})>'.format(', '.join('{}={}'.format(a, getattr(self, a)) for a in attrs))


def hash_id(*args, **kwargs):
    sha256 = kwargs.pop('sha256', False)
    assert len(kwargs) == 0, 'unexpected keywords args: {}'.format(kwargs)
    to_hash = '_'.join(map(str, args))
    to_hash = to_hash.encode()
    if sha256:
        return hashlib.sha256(to_hash).hexdigest()
    else:
        return hashlib.sha1(to_hash).hexdigest()


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
            await action.prepare(self.ds)

        args = set(inspect.signature(func).parameters)
        args.remove('action')
        if args != set(kwargs):
            raise BadDataException('Wrong kwargs for {}, got: {}, expected: {}'.format(func.__name__, kwargs, args))
        return await func(action, **kwargs)

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
        await action.ds.save_event(action, save_data, timestamp)
        if action.remote:
            return
        status = await action.ds.get_status()
        if status == Conversations.Status.DRAFT:
            return
        propagate_data = self._subdict(data, 'pb')
        await self.prop.propagate(action, propagate_data, timestamp)

    def __repr__(self):
        return '<Controller({})>'.format(self.ref)


class Conversations:
    name = Components.CONVERSATIONS
    event = None
    schema = {
        'creator': {'type': 'string', 'required': True},
        'timestamp': {'type': 'datetime', 'required': True},
        'ref': {'type': 'string', 'required': True},
        'status': {'type': 'string', 'required': True},
        'subject': {'type': 'string', 'required': True},
        'expiration': {'type': 'datetime', 'nullable': True, 'required': True},
        'messages': {
            'type': 'list',
            'schema': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'id': {'type': 'string', 'required': True},
                    'author': {'type': 'integer', 'required': True},
                    'parent': {'type': 'string', 'nullable': True, 'required': True},
                    'timestamp': {'type': 'datetime', 'required': True},
                    'body': {'type': 'string', 'required': True},
                }
            }
        },
        'participants': {
            'type': 'list',
            'required': True,
            'schema': {'type': 'list', 'minlength': 2, 'maxlength': 2, 'required': True}
        },
    }

    def __init__(self, controller):
        self.controller = controller

    class Status:
        DRAFT = 'draft'
        PENDING = 'pending'
        ACTIVE = 'active'
        EXPIRED = 'expired'
        DELETED = 'deleted'

    @property
    def _participants(self):
        return self.controller.components[Components.PARTICIPANTS]

    @property
    def _messages(self):
        return self.controller.components[Components.MESSAGES]

    async def create(self, creator, subject, body=None, ref=None):
        timestamp = self.controller.now_tz()
        ref = ref or subject
        con_id = self._con_id_hash(creator, timestamp, ref)
        await self._create(creator, timestamp, ref, subject, self.Status.DRAFT, con_id)

        ds = self._create_ds(con_id)
        creator_id = await self._participants.add_first(ds, creator)

        if body:
            await self._messages.add_basic(ds, creator, creator_id, body, None)
        return con_id

    async def add(self, action, data):
        """
        Add a new conversation created on another platform.
        """
        v = Validator(self.schema, )
        if not isinstance(data, dict):
            raise MisshapedDataException('data must be a dict')
        if not v(data):
            raise MisshapedDataException('{}'.format(v.errors))
        creator = data['creator']
        timestamp = data['timestamp']
        check_con_id = self._con_id_hash(creator, timestamp, data['ref'])
        if check_con_id != action.con:
            raise BadHash('provided hash {} does not match computed hash {}'.format(action.con, check_con_id))
        con_id = action.con
        await self._create(creator, timestamp, data['ref'], data['subject'], self.Status.PENDING, con_id=con_id)

        ds = self._create_ds(con_id)

        participant_data = data[Components.PARTICIPANTS]
        await self._participants.add_multiple(ds, participant_data)

        message_data = data[Components.MESSAGES]
        await self._messages.add_multiple(ds, message_data)

    async def publish(self, action):
        await action.ds.set_status(self.Status.ACTIVE)

        ref = await action.ds.get_ref()
        timestamp = self.controller.now_tz()

        new_con_id = self._con_id_hash(action.actor_addr, timestamp, ref)
        await action.ds.set_published_id(timestamp, new_con_id)

        new_action = Action(action.actor_addr, new_con_id, Verbs.ADD, Components.CONVERSATIONS)
        await new_action.prepare(self.controller.ds)

        data = await action.ds.export()
        await self.controller.event(new_action, timestamp=timestamp, p_data=data)

    async def get_by_id(self, id):
        raise NotImplementedError()

    async def _create(self, creator, timestamp, ref, subject, status, con_id):
        await self.controller.ds.create_conversation(
            con_id=con_id,
            creator=creator,
            timestamp=timestamp,
            ref=ref,
            subject=subject,
            status=status,
        )
        logger.info('created %s conversation %s..., creator: "%s", subject: "%s"', status, con_id[:6], creator, subject)

    def _create_ds(self, con_id):
        return self.controller.ds.new_con_ds(con_id)

    def _con_id_hash(self, creator, timestamp, ref):
        return hash_id(creator, timestamp.isoformat(), ref, sha256=True)

    def __repr__(self):
        return '<Conversations on {}>'.format(self.controller)


class _Component:
    name = None

    def __init__(self, controller):
        self.controller = controller

    async def _event(self, *args, **kwargs):
        return await self.controller.event(*args, **kwargs)

    def __repr__(self):
        return '<{} on controller "{}">'.format(self.__class__.__name__, self.controller.ref)


class Messages(_Component):
    name = Components.MESSAGES

    async def add_multiple(self, ds, data):
        if data[0]['parent'] is not None:
            raise MisshapedDataException('first message parent should be None')

        parents = {data[0]['id']: data[0]['timestamp']}
        for d in data[1:]:
            parent = parents.get(d['parent'])
            if parent is None:
                raise ComponentNotFound('message {} not found in {}'.format(d['parent'], parents.keys()))
            if parent >= d['timestamp']:
                raise BadDataException('timestamp not after parent timestamp: {timestamp}'.format(**d))
            parents[d['id']] = d['timestamp']
            # TODO check authors exist

        await ds.add_multiple_components(self.name, data)

    async def add_basic(self, ds, author, author_id, body, parent_id):
        timestamp = self.controller.now_tz()
        m_id = hash_id(author, timestamp.isoformat(), body, parent_id)
        await ds.add_component(
            self.name,
            id=m_id,
            author=author_id,
            timestamp=timestamp,
            body=body,
            parent=parent_id,
        )
        return m_id, timestamp

    async def add(self, action, body, parent_id):
        # TODO this remote vs. not remote logic should be pretty common, can it be reused?
        await action.ds.get_message_author(parent_id)
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE access required to add messages')
        timestamp = None
        if action.remote:
            # TODO check parent_id and timestamp
            await action.ds.add_component(
                self.name,
                id=action.item,
                author=action.actor_id,
                timestamp=action.timestamp,
                body=body,
                parent=parent_id,
            )
        else:
            action.item, timestamp = await self.add_basic(action.ds, action.actor_addr, action.actor_id, body,
                                                          parent_id)
        await self._event(action, timestamp=timestamp, p_parent_id=parent_id, p_body=body)

    async def edit(self, action, body):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.edit_component(self.name, action.item, body=body)
        await self._event(action, b_value=body)

    async def delta_edit(self, action, body):
        raise NotImplementedError()

    async def delete(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.delete_component(self.name, action.item)
        await self._event(action)

    async def lock(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.lock_component(self.name, action.item)
        await self._event(action)

    async def unlock(self, action):
        await self._check_permissions(action)
        if not await action.ds.get_message_locked(self.name, action.item):
            raise ComponentNotLocked('{} with id = {} not locked'.format(self.name, action.item))
        await action.ds.unlock_component(self.name, action.item)
        await self._event(action)

    async def _check_permissions(self, action):
        if action.perm == perms.WRITE:
            author_pid = await action.ds.get_message_author(action.item)
            if author_pid != action.actor_id:
                raise InsufficientPermissions('To {} a message authored by another participant '
                                              'FULL permissions are requires'.format(action.verb))
        elif action.perm != perms.FULL:
            raise InsufficientPermissions('To {} a message requires FULL or WRITE permissions'.format(action.verb))

    async def _check_locked(self, action):
        if await action.ds.get_message_locked(self.name, action.item):
            raise ComponentLocked('{} with id = {} locked'.format(self.name, action.item))


class Participants(_Component):
    name = Components.PARTICIPANTS

    class Permissions:
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    async def add_multiple(self, ds, data):
        # TODO validate
        prepared_data = [{'address': address, 'permissions': permissions} for address, permissions in data]
        await ds.add_multiple_components(self.name, prepared_data)
        for address, _ in data:
            await self.controller.prop.add_participant(ds.con, address)

    async def add_first(self, ds, address):
        new_participant_id = await ds.add_component(
            self.name,
            address=address,
            permissions=perms.FULL,
        )
        logger.info('first participant added to %d: address: "%s"', ds.con, address)
        return new_participant_id

    async def add(self, action, address, permissions):
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE permission are required to add participants')
        if action.perm == perms.WRITE and permissions == perms.FULL:
            raise InsufficientPermissions('FULL permission are required to add participants with FULL permissions')
        # TODO check the address is valid
        new_participant_id = await action.ds.add_component(
            self.name,
            address=address,
            permissions=permissions,
        )
        logger.info('added participant to %d: address: "%s", permissions: "%s"', action.con, address, permissions)
        await self.controller.prop.add_participant(action.con, address)
        await self._event(action, new_participant_id)
        return new_participant_id

# shortcut
perms = Participants.Permissions
