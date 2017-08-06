import base64
import hashlib
import os
from enum import Enum, unique
from typing import NamedTuple

import asyncpg
from asyncpg.pool import Pool  # noqa

from . import Settings
from .utils.encoding import to_unix_ms


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
