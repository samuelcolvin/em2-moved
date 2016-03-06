import logging
import datetime
import inspect
import json

import pytz
from cerberus import Validator

from .exceptions import ComponentNotFound, VerbNotFound, BadDataException, BadHash, MisshapedDataException
from .datastore import DataStore
from .propagator import BasePropagator
from .common import Components
from .enums import Enum
from .components import Messages, Participants, hash_id

logger = logging.getLogger('em2')


class Verbs(Enum):
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
    def __init__(self, actor, conversation, verb, component,
                 item=None, timestamp=None, event_id=None, parent_event_id=None):
        self.ds = None
        self.actor_id = None
        self.perm = None
        self.actor_addr = actor
        self.conv = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.event_id = event_id
        self.parent_event_id = parent_event_id

    @property
    def is_remote(self):
        return self.event_id is not None

    async def prepare(self):
        self.actor_id, self.perm = await self.ds.get_participant(self.actor_addr)

    def calc_event_id(self):
        return hash_id(self.timestamp, self.actor_addr, self.conv, self.verb, self.component, self.item)

    def __repr__(self):
        attrs = ['actor_addr', 'actor_id', 'perm', 'conv', 'verb', 'component', 'item', 'timestamp',
                 'event_id', 'parent_event_id']
        return '<Action({})>'.format(', '.join('{}={}'.format(a, getattr(self, a)) for a in attrs))


class Controller:
    """
    Top level class for accessing conversations and conversation components.
    """
    def __init__(self, datastore, propagator, timezone_name='utc', ref=None):
        assert isinstance(datastore, DataStore)
        assert isinstance(propagator, BasePropagator)
        self.ds = datastore
        self.prop = propagator
        self.timezone_name = timezone_name
        self.ref = ref if ref is not None else hex(id(self))
        self.conversations = Conversations(self)
        components = [Messages, Participants]
        self.components = {c.name: c(self) for c in components}
        self.valid_verbs = set(Verbs.__values__)

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

        if action.is_remote:
            if action.event_id != action.calc_event_id():
                raise BadHash('event_id "{}" incorrect'.format(action.event_id))
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
        event_id = action.calc_event_id()
        await action.ds.save_event(event_id, action, save_data)
        status = await action.ds.get_status()
        if status == Conversations.Status.DRAFT:
            return
        # TODO some way to propagate events to clients here
        if action.is_remote:
            return
        propagate_data = self._subdict(data, 'pb')
        # FIXME what happens when propagation fails, perhaps save status on update
        await self.prop.propagate(action, event_id, propagate_data, action.timestamp)

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

    class Status(Enum):
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
        """
        Create a brand new conversation.
        """
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
                action = Action(creator, conv_id, Verbs.ADD, Components.MESSAGES, timestamp=timestamp)
                action.actor_id = creator_id
                action.ds = cds
                action.item = await self._messages.add_basic(action, body, None)
                await self.controller.event(action)
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
        """
        AKA Send. Update a conversation (from draft) to active and tell other participants (and their platforms)
        about it.
        """
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
