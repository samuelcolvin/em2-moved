import logging
import json

from cerberus import Validator

from .exceptions import BadHash, MisshapedDataException
from .enums import Enum
from .components import Components, hash_id
from .interactions import Action, Verbs

logger = logging.getLogger('em2')


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
                action.cds = cds
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
        await action.cds.set_status(self.Status.ACTIVE)

        ref = await action.cds.get_ref()

        new_conv_id = self._conv_id_hash(action.actor_addr, action.timestamp, ref)
        await action.cds.set_published_id(action.timestamp, new_conv_id)

        new_action = Action(action.actor_addr, new_conv_id, Verbs.ADD, Components.CONVERSATIONS,
                            timestamp=action.timestamp)
        new_action.cds, new_action.actor_id, new_action.perm = action.cds, action.actor_id, action.perm

        data = await action.cds.export()
        await self.controller.event(new_action, p_data=data)

    async def get_by_id(self, id):
        raise NotImplementedError()

    def _conv_id_hash(self, creator, timestamp, ref):
        return hash_id(creator, timestamp.isoformat(), ref, sha256=True)

    def __repr__(self):
        return '<Conversations 0x{:x} on {}>'.format(id(self), self.controller)
