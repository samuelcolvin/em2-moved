import base64
import hashlib
import os
from datetime import datetime
from enum import Enum, unique
from typing import NamedTuple, Optional

import asyncpg
from aiohttp.web_exceptions import HTTPBadRequest
from asyncpg.pool import Pool  # noqa
from pydantic import EmailStr, NoneStr, constr

from . import Settings
from .utils.encoding import to_unix_ms
from .utils.web import FetchVal404Mixin, WebModel


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


class ApplyAction(FetchVal404Mixin):
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

    __slots__ = 'conn',

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
                self.data.body,
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
