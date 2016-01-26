import logging
import datetime
import hashlib
import inspect
import json

import pytz
from cerberus import Validator

from .exceptions import (InsufficientPermissions, ComponentNotFound, VerbNotFound, ComponentNotLocked,
                         ComponentLocked, BadDataException, BadHash, MisshapedDataException)
from .utils import get_options
from .data_store import DataStore
from .propagator import BasePropagator
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
        self.conv = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.remote = remote

    async def prepare(self):
        self.actor_id, self.perm = await self.ds.get_participant(self.actor_addr)
        return self.ds

    def __repr__(self):
        attrs = ['actor_addr', 'actor_id', 'perm', 'conv', 'verb', 'component', 'item', 'timestamp', 'remote']
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
        self.ref = ref if ref is not None else hex(id(self))
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

        if action.remote:
            if not isinstance(action.timestamp, datetime.datetime):
                raise BadDataException('remote actions should always have a timestamp')
        else:
            action.timestamp = self.now_tz()

        func = getattr(component_cls, action.verb, None)
        if func is None:
            raise VerbNotFound('{} is not an available verb on {}'.format(action.verb, action.component))

        args = set(inspect.signature(func).parameters)
        args.remove('action')
        if args != set(kwargs):
            msg = 'Wrong kwargs for {}, got: {}, expected: {}'
            raise BadDataException(msg.format(func.__name__, sorted(list(kwargs)), sorted(list(args))))

        # TODO better way of dealing with this(ese) case(s)
        if action.component == Components.CONVERSATIONS and action.verb == Verbs.ADD:
            return await func(action, **kwargs)

        async with self.ds.connection() as conn:
            action.ds = self.ds.new_conv_ds(action.conv, conn)
            await action.prepare()
            return await func(action, **kwargs)

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    def _subdict(self, data, first_chars):
        return {k[2:]: v for k, v in data.items() if k[0] in first_chars}

    async def event(self, action, **data):
        """
        Record and propagate updates of conversations and conversation components.

        :param action: Action instance
        :param data: extra information to either be saved (s_*), propagated (p_*) or both (b_*)
        """
        logger.debug('event on %d: author: "%s", action: "%s", component: %s %s',
                     action.conv, action.actor_addr, action.verb, action.component, action.item)
        save_data = self._subdict(data, 'sb')
        await action.ds.save_event(action, save_data)
        if action.remote:
            return
        status = await action.ds.get_status()
        if status == Conversations.Status.DRAFT:
            return
        propagate_data = self._subdict(data, 'pb')
        # FIXME what do we do when propagation fails, can we save status on update
        await self.prop.propagate(action, propagate_data, action.timestamp)

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
        'expiration': {'type': 'datetime', 'nullable': True},
        'messages': {
            'type': 'list',
            'schema': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'id': {'type': 'string', 'required': True},
                    'author': {'type': 'string', 'required': True},
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
        conv_id = self._conv_id_hash(creator, timestamp, ref)
        async with self.controller.ds.connection() as conn:
            await self.controller.ds.create_conversation(
                conn,
                conv_id=conv_id,
                creator=creator,
                timestamp=timestamp,
                ref=ref,
                subject=subject,
                status=self.Status.DRAFT,
            )
            logger.info('created draft conversation %s..., creator: "%s"', conv_id[:6], creator)

            cds = self.controller.ds.new_conv_ds(conv_id, conn)
            creator_id = await self._participants.add_first(cds, creator)

            if body:
                await self._messages.add_basic(cds, timestamp, creator, creator_id, body, None)
        return conv_id

    async def add(self, action, data):
        """
        Add a new conversation created on another platform.
        """
        if not isinstance(data, dict):
            raise MisshapedDataException('data must be a dict')

        v = Validator(self.schema)
        if not v(data):
            raise MisshapedDataException(json.dumps(v.errors, sort_keys=True))

        creator = data['creator']
        timestamp = data['timestamp']
        check_conv_id = self._conv_id_hash(creator, timestamp, data['ref'])
        if check_conv_id != action.conv:
            raise BadHash('provided hash {} does not match computed hash {}'.format(action.conv, check_conv_id))
        async with self.controller.ds.connection() as conn:
            await self.controller.ds.create_conversation(
                conn,
                conv_id=action.conv,
                creator=creator,
                timestamp=timestamp,
                ref=data['ref'],
                subject=data['subject'],
                status=self.Status.PENDING,
            )
            logger.info('created pending conversation %s..., creator: "%s"', action.conv[:6], creator)

            ds = self.controller.ds.new_conv_ds(action.conv, conn)

            participant_data = data[Components.PARTICIPANTS]
            await self._participants.add_multiple(ds, participant_data)

            message_data = data[Components.MESSAGES]
            await self._messages.add_multiple(ds, message_data)

    async def publish(self, action):
        await action.ds.set_status(self.Status.ACTIVE)

        ref = await action.ds.get_ref()

        new_conv_id = self._conv_id_hash(action.actor_addr, action.timestamp, ref)
        await action.ds.set_published_id(action.timestamp, new_conv_id)

        new_action = Action(action.actor_addr, new_conv_id, Verbs.ADD, Components.CONVERSATIONS,
                            timestamp=action.timestamp)
        new_action.ds, new_action.actor_id, new_action.perm = action.ds, action.actor_id, action.perm

        data = await action.ds.export()
        await self.controller.event(new_action, p_data=data)

    async def get_by_id(self, id):
        raise NotImplementedError()

    def _conv_id_hash(self, creator, timestamp, ref):
        return hash_id(creator, timestamp.isoformat(), ref, sha256=True)

    def __repr__(self):
        return '<Conversations 0x{:x} on {}>'.format(id(self), self.controller)


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

        participants = await ds.get_all_component_items(Components.PARTICIPANTS)
        participants = {p['address']: p['id'] for p in participants}
        for d in data:
            d['author'] = participants[d['author']]

        await ds.add_multiple_components(self.name, data)

    async def add_basic(self, ds, timestamp, author, author_id, body, parent_id):
        m_id = hash_id(author, timestamp.isoformat(), body, parent_id)
        await ds.add_component(
            self.name,
            id=m_id,
            author=author_id,
            timestamp=timestamp,
            body=body,
            parent=parent_id,
        )
        return m_id

    async def add(self, action, body, parent_id):
        meta = await action.ds.get_message_meta(parent_id)
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE access required to add messages')

        if action.timestamp <= meta['timestamp']:
            raise BadDataException('timestamp not after parent timestamp: {}'.format(action.timestamp))

        if action.remote:
            await action.ds.add_component(
                self.name,
                id=action.item,
                author=action.actor_id,
                timestamp=action.timestamp,
                body=body,
                parent=parent_id,
            )
        else:
            action.item = await self.add_basic(action.ds, action.timestamp, action.actor_addr, action.actor_id, body,
                                               parent_id)
        await self._event(action, p_parent_id=parent_id, p_body=body)

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
        if not await action.ds.check_component_locked(self.name, action.item):
            raise ComponentNotLocked('{} with id = {} not locked'.format(self.name, action.item))
        await action.ds.unlock_component(self.name, action.item)
        await self._event(action)

    async def _check_permissions(self, action):
        if action.perm == perms.WRITE:
            meta = await action.ds.get_message_meta(action.item)
            author_pid = meta['author']
            if author_pid != action.actor_id:
                raise InsufficientPermissions('To {} a message authored by another participant '
                                              'FULL permissions are requires'.format(action.verb))
        elif action.perm != perms.FULL:
            raise InsufficientPermissions('To {} a message requires FULL or WRITE permissions'.format(action.verb))

    async def _check_locked(self, action):
        if await action.ds.check_component_locked(self.name, action.item):
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
            await self.controller.prop.add_participant(ds.conv, address)

    async def add_first(self, ds, address):
        new_participant_id = await ds.add_component(
            self.name,
            address=address,
            permissions=perms.FULL,
        )
        logger.info('first participant added to %d: address: "%s"', ds.conv, address)
        return new_participant_id

    async def add(self, action, address, permissions):
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE permission are required to add participants')
        if action.perm == perms.WRITE and permissions == perms.FULL:
            raise InsufficientPermissions('FULL permission are required to add participants with FULL permissions')
        # TODO check the address is valid
        action.item = await action.ds.add_component(
            self.name,
            address=address,
            permissions=permissions,
        )
        logger.info('added participant to %d: address: "%s", permissions: "%s"', action.conv, address, permissions)
        await self.controller.prop.add_participant(action.conv, address)
        await self._event(action)
        return action.item

# shortcut
perms = Participants.Permissions
