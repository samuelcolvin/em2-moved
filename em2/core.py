import base64
import hashlib
import logging
import os
from datetime import datetime
from enum import Enum, unique
from typing import List, NamedTuple, Optional

import asyncpg
from aiohttp.web_exceptions import HTTPBadRequest
from asyncpg.pool import Pool  # noqa
from pydantic import BaseModel, EmailStr, NoneStr, ValidationError, constr

from . import Settings
from .utils.encoding import to_unix_ms
from .utils.web import FetchOr404Mixin, WebModel

logger = logging.getLogger('em2.core')


def generate_conv_key(creator, ts, subject):
    return generate_hash(creator, to_unix_ms(ts), subject, sha256=True)


def generate_hash(*args, sha256=False):
    to_hash = '_'.join(map(str, args)).encode()
    if sha256:
        return hashlib.sha256(to_hash).hexdigest()
    else:
        return hashlib.sha1(to_hash).hexdigest()


def gen_random(prefix):
    """
    :param prefix: string to prefix random key with
    :return: prefix plus 16 char alphanumeric (lowercase) random string
    """
    # TODO move to untils
    return prefix + '-' + base64.b32encode(os.urandom(10))[:16].decode().lower()


@unique
class Components(str, Enum):
    """
    Component types, used for both urls and in db ENUM see models.sql
    """
    SUBJECT = 'subject'
    EXPIRY = 'expiry'
    LABEL = 'label'
    MESSAGE = 'message'
    PARTICIPANT = 'participant'
    ATTACHMENT = 'attachment'


@unique
class Verbs(str, Enum):
    """
    Verb types, used for both urls and in db ENUM see models.sql
    """
    ADD = 'add'
    MODIFY = 'modify'
    DELETE = 'delete'
    RECOVER = 'recover'
    LOCK = 'lock'
    UNLOCK = 'unlock'


@unique
class Relationships(str, Enum):
    sibling = 'sibling'
    child = 'child'


class Database:
    def __init__(self, settings: Settings, loop):
        self._loop = loop
        self._settings = settings
        self._pool: Pool = None

    async def startup(self):
        self._pool = await asyncpg.create_pool(
            dsn=self._settings.pg_dsn,
            min_size=self._settings.PG_POOL_MINSIZE,
            max_size=self._settings.PG_POOL_MAXSIZE,
            loop=self._loop,
        )

    def acquire(self, *, timeout=None):
        return self._pool.acquire(timeout=timeout)

    async def close(self):
        return await self._pool.close()


class Action(NamedTuple):
    action_key: str
    conv_key: str
    conv_id: int
    verb: Verbs
    component: Components
    actor: str
    timestamp: str
    parent: str
    body: str
    relationship: Relationships
    item: str


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update here should happen very rarely
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def get_create_recipient(conn, address):
    recipient_id = await conn.fetchval(GET_RECIPIENT_ID, address)
    if recipient_id is None:
        recipient_id = await conn.fetchval(SET_RECIPIENT_ID, address)
    return recipient_id


GET_EXISTING_RECIPS_SQL = 'SELECT address, id FROM recipients WHERE address = any($1)'
SET_MISSING_RECIPS_SQL = """
INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
RETURNING address, id
"""


async def create_missing_recipients(conn, addresses):
    part_addresses = set(addresses)
    prts = {}
    for address, id in await conn.fetch(GET_EXISTING_RECIPS_SQL, part_addresses):
        prts[address] = id
        part_addresses.remove(address)

    if part_addresses:
        prts.update(dict(await conn.fetch(SET_MISSING_RECIPS_SQL, part_addresses)))
    return prts


class ApplyAction(FetchOr404Mixin):
    class Data(WebModel):
        action_key: constr(min_length=20, max_length=20)
        conv: int
        verb: Verbs
        component: Components
        actor: int
        timestamp: Optional[datetime] = None
        item: Optional[constr(max_length=255)] = None
        parent: Optional[constr(min_length=20, max_length=20)] = None
        body: NoneStr = None
        relationship: Optional[Relationships] = None  # TODO check relationship is set when required
        # TODO: participant permissions and more exotic types
        # TODO: add timezone event originally occurred in

    create_action_sql = """
    INSERT INTO actions (key, conv, verb, component, actor, parent, part, message, body, timestamp)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id
    """
    create_action_create_ts_sql = """
    INSERT INTO actions (key, conv, verb, component, actor, parent, part, message, body)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    RETURNING id, to_json(timestamp)
    """

    def __init__(self, conn, remote_action, **data):
        self.conn = conn
        self._remote_action = remote_action
        self.data = self.Data(**data)
        self.item_key = None
        self.action_id = None
        self.action_timestamp = None

    async def run(self):
        if self.data.component in (Components.MESSAGE, Components.PARTICIPANT) and not self.data.item:
            # TODO replace with method validation on Data
            raise HTTPBadRequest(text=f'item may not be null for {self.data.component} actions')

        self.item_key, prt_id, message_id, parent_id = None, None, None, None
        async with self.conn.transaction():
            if self.data.component is Components.MESSAGE:
                if self.data.verb is Verbs.ADD:
                    self.item_key, message_id = await self._add_message()
                else:
                    self.item_key, message_id, parent_id = await self._mod_message()
            elif self.data.component is Components.PARTICIPANT:
                if self.data.verb is Verbs.ADD:
                    self.item_key, prt_id = await self._add_participant()
                else:
                    self.item_key, prt_id = await self._mod_participant()
            else:
                raise NotImplementedError()

            args = (
                self.data.action_key,
                self.data.conv,
                self.data.verb,
                self.data.component,
                self.data.actor,
                parent_id,
                prt_id,
                message_id,
                self.data.body if self.data.component == Components.MESSAGE else None,
            )
            if self._remote_action:
                args += self.data.timestamp.replace(tzinfo=None),
                self.action_id = await self.conn.fetchval(self.create_action_sql, *args)
            else:
                self.action_id, action_timestamp = await self.conn.fetchrow(self.create_action_create_ts_sql, *args)
                # remove quotes added by to_json
                self.action_timestamp = action_timestamp[1:-1]

    _find_msg_by_action_sql = """
    SELECT m.id
    FROM actions AS a
    JOIN messages AS m ON a.message = m.id
    WHERE a.conv = $1 AND a.key = $2
    """
    _check_msg_actions_sql = """
    SELECT id FROM actions
    WHERE conv = $1 and message IS NOT NULL
    LIMIT 1
    """
    _get_first_msg_sql = """
    SELECT id FROM messages
    WHERE conv = $1
    LIMIT 2
    """
    _add_message_sql = """
    INSERT INTO messages (key, conv, after, relationship, body) VALUES ($1, $2, $3, $4, $5)
    RETURNING id
    """

    async def _add_message(self):
        if self.data.parent:
            after_id = await self.fetchval404(self._find_msg_by_action_sql, self.data.conv, self.data.parent)
        else:
            # the only valid case here is that there's no action for messages
            if await self.conn.fetchval(self._check_msg_actions_sql, self.data.conv):
                raise HTTPBadRequest(text='parent may not be null if actions already exist')
            msg_ids = await self.conn.fetch(self._get_first_msg_sql, self.data.conv)
            if len(msg_ids) != 1:
                raise HTTPBadRequest(text=f'only one message should exist if parent is null: {len(msg_ids)}')
            after_id = msg_ids[0][0]

        if not self.data.body:
            raise HTTPBadRequest(text='body can not be empty when adding a message')
        if self._remote_action:
            item_key = self.data.item
        else:
            item_key = gen_random('msg')
        args = item_key, self.data.conv, after_id, self.data.relationship, self.data.body
        message_id = await self.conn.fetchval(self._add_message_sql, *args)
        return item_key, message_id

    _find_message_by_key_sql = """
    SELECT m.id
    FROM messages AS m
    WHERE m.conv = $1 AND m.key = $2
    """
    _latest_message_action_sql = """
    SELECT id, key, verb, actor
    FROM actions
    WHERE conv = $1 AND message = $2
    ORDER BY id DESC
    LIMIT 1
    """
    _delete_recover_message_sql = 'UPDATE messages SET active = $1 WHERE id = $2'
    _modify_message_sql = 'UPDATE messages SET body = $1 WHERE id = $2'

    async def _mod_message(self):
        message_key = self.data.item
        message_id = await self.fetchval404(self._find_message_by_key_sql, self.data.conv, message_key)
        parent_id, parent_key, parent_verb, parent_actor = await self.fetchrow404(
            self._latest_message_action_sql,
            self.data.conv,
            message_id
        )
        if self.data.parent != parent_key:
            raise HTTPBadRequest(text=f'parent does not match latest action on the message: {parent_key}')

        if parent_actor != self.data.actor and parent_verb == Verbs.LOCK:
            raise HTTPBadRequest(text=f'message {self.data.item} is locked and cannot be updated')
        # could do more validation here to enforce:
        # * locking before modification
        # * not modifying deleted messages
        # * not repeatedly recovering messages
        if self.data.verb in (Verbs.DELETE, Verbs.RECOVER):
            await self.conn.execute(self._delete_recover_message_sql, self.data.verb == Verbs.RECOVER, message_id)
        elif self.data.verb == Verbs.MODIFY:
            if not self.data.body:
                raise HTTPBadRequest(text='body can not be empty when modifying a message')
            await self.conn.execute(self._modify_message_sql, self.data.body, message_id)
        # lock and unlock don't change the message
        return message_key, message_id, parent_id

    _get_recipient_id_sql = 'SELECT id FROM recipients WHERE address = $1'
    _set_recipient_id_sql = """
    INSERT INTO recipients (address) VALUES ($1)
    ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
    """
    _add_participant_sql = """
    INSERT INTO participants (conv, recipient) VALUES ($1, $2)
    ON CONFLICT DO NOTHING RETURNING id
    """

    async def _add_participant(self):
        try:
            part_address = EmailStr.validate(self.data.item)
        except (TypeError, ValueError):
            raise HTTPBadRequest(text='is not a valid email address')

        recipient_id = await self.conn.fetchval(self._get_recipient_id_sql, part_address)
        if recipient_id is None:
            recipient_id = await self.conn.fetchval(self._set_recipient_id_sql, part_address)
        prt_id = await self.conn.fetchval(self._add_participant_sql, self.data.conv, recipient_id)
        if prt_id is None:
            raise HTTPBadRequest(text='participant already exists on the conversation')
        return part_address, prt_id

    _find_participant_sql = """
    SELECT p.id FROM participants AS p
    JOIN recipients AS r ON p.recipient = r.id
    WHERE p.conv = $1 AND r.address = $2
    """
    _delete_participant_sql = 'UPDATE participants SET active = $1 WHERE id = $2'

    async def _mod_participant(self):
        # TODO check parent matches latest data.parent
        part_address = self.data.item
        prt_id = await self.fetchval404(self._find_participant_sql, self.data.conv, part_address)
        if self.data.verb in (Verbs.DELETE, Verbs.RECOVER):
            await self.conn.execute(self._delete_participant_sql, self.data.verb == Verbs.RECOVER, prt_id)
        elif self.data.verb is Verbs.MODIFY:
            raise NotImplementedError()
        else:
            raise HTTPBadRequest(text=f'Invalid verb for participants, can only add, delete, recover or modify')
        return part_address, prt_id


class GetConv(FetchOr404Mixin):
    get_conv_id_sql = """
    SELECT c.id FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    JOIN recipients AS r ON p.recipient = r.id
    WHERE r.address = $1 AND c.key = $2 AND p.active = True
    """

    conv_details_sql = """
    SELECT row_to_json(t)
    FROM (
      SELECT c.key AS key, c.subject AS subject, c.timestamp AS ts, r.address AS creator, c.published AS published
      FROM conversations AS c
      JOIN recipients AS r ON c.creator = r.id
      WHERE c.id = $1
    ) t;
    """

    messages_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT m1.key AS key, m2.key AS after, m1.relationship AS relationship, m1.active AS active, m1.body AS body
      FROM messages AS m1
      LEFT JOIN messages AS m2 ON m1.after = m2.id
      WHERE m1.conv = $1 AND m1.active = True
    ) t;
    """

    participants_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT r.address AS address, p.readall AS readall
      FROM participants AS p
      JOIN recipients AS r ON p.recipient = r.id
      WHERE p.conv = $1 AND p.active = True
    ) t;
    """

    actions_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT a.key AS key, a.verb AS verb, a.component AS component, a.body AS body, a.timestamp AS timestamp,
      actor_recipient.address AS actor,
      a_parent.key AS parent,
      m.key AS message,
      prt_recipient.address AS participant
      FROM actions AS a

      LEFT JOIN actions AS a_parent ON a.parent = a_parent.id
      LEFT JOIN messages AS m ON a.message = m.id

      JOIN participants AS actor_prt ON a.actor = actor_prt.id
      JOIN recipients AS actor_recipient ON actor_prt.recipient = actor_recipient.id

      LEFT JOIN participants AS prt_prt ON a.part = prt_prt.id
      LEFT JOIN recipients AS prt_recipient ON prt_prt.recipient = prt_recipient.id

      WHERE a.conv = $1
    ) t;
    """

    def __init__(self, conn):
        self.conn = conn

    async def run(self, conv_key, participant_address):
        conv_id = await self.fetchval404(
            self.get_conv_id_sql,
            participant_address,
            conv_key,
            msg=f'conversation {conv_key} not found'
        )
        details = await self.conn.fetchval(self.conv_details_sql, conv_id)
        messages = await self.conn.fetchval(self.messages_sql, conv_id)
        parts = await self.conn.fetchval(self.participants_sql, conv_id)
        actions = await self.conn.fetchval(self.actions_sql, conv_id)
        return (
            '{'
            f'"details":{details},'
            f'"messages":{messages},'
            f'"participants":{parts},'
            f'"actions":{actions or "null"}'
            '}'
        )


class _ConvDetails(BaseModel):
    key: constr(max_length=64)
    creator: EmailStr
    subject: constr(max_length=255)
    ts: datetime  # TODO check this is less than now
    published: bool  # not actually used, in foreign -> create conv, assumed true


class _Participant(BaseModel):
    address: EmailStr
    readall: bool


class _ConvMessage(BaseModel):
    key: constr(min_length=20, max_length=20)
    active: bool
    body: str
    after: Optional[constr(min_length=20, max_length=20)] = None
    relationship: Optional[Relationships] = None


class _Action(BaseModel):
    key: constr(min_length=20, max_length=20)
    verb: Verbs
    component: Components
    body: NoneStr
    timestamp: datetime
    actor: EmailStr
    parent: Optional[constr(min_length=20, max_length=20)]
    message: Optional[constr(min_length=20, max_length=20)]
    participant: Optional[EmailStr]


class FullConv(BaseModel):
    details: _ConvDetails
    participants: List[_Participant]
    messages: List[_ConvMessage]
    actions: Optional[List[_Action]] = None


class CreateForeignConv:
    create_conv_sql = """
    INSERT INTO conversations (key, creator, subject, timestamp, published)
    VALUES ($1, $2, $3, $4, TRUE) RETURNING id
    """
    add_participants_sql = 'INSERT INTO participants (conv, recipient, readall) VALUES ($1, $2, $3)'
    add_message_sql = """
    INSERT INTO messages (conv, key, body, active, after, relationship)
    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
    """
    create_action_sql = """
    INSERT INTO actions (key, conv, verb, component, actor, parent, part, message, body, timestamp)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id
    """

    def __init__(self, conn):
        self.conn = conn

    async def run(self, data):
        try:
            conv = FullConv(**data)
        except ValidationError as e:
            return logger.warning('invalid conversation data:\n%s', e)

        async with self.conn.transaction():
            await self._trans(conv)

    async def _trans(self, conv: FullConv):
        deets = conv.details

        creator_recip_id = await get_create_recipient(self.conn, deets.creator)
        conv_id = await self.conn.fetchval(self.create_conv_sql, deets.key, creator_recip_id, deets.subject, deets.ts)

        recip_id = await create_missing_recipients(self.conn, [p.address for p in conv.participants])
        await self.conn.executemany(
            self.add_participants_sql,
            {(conv_id, recip_id[p.address], p.readall) for p in conv.participants}
        )

        msg_lookup = {}
        for msg in conv.messages:
            after_id = None
            if msg.after:
                # TODO deal with KeyError
                after_id = msg_lookup[msg.after]
            msg_lookup[msg.key] = await self.conn.fetchval(
                self.add_message_sql,
                conv_id, msg.key, msg.body, msg.active, after_id, msg.relationship
            )

        # recip_id[deets.creator] = creator_recip_id
        # action_lookup = {}
        # for action in conv.actions:
        #     args = (
        #         action.key,
        #         conv_id,
        #         action.verb,
        #         action.component,
        #         recip_id[action.actor],  # FIXME this is wrong
        #         action.parent and action_lookup[action.parent],
        #         prt_id,
        #         action.message and msg_lookup[action.message],
        #         action.body if action.component == Components.MESSAGE else None,
        #         action.timestamp
        #     )
