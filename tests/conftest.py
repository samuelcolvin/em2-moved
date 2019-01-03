import asyncio
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import asyncpg
import pytest
from aiohttp.test_utils import teardown_test_loop
from aioredis import create_redis
from pydantic.datetime_parse import parse_datetime

from em2 import Settings
from em2.core import get_create_recipient
from em2.utils.database import prepare_database

from .fixture_classes.foreign_server import create_test_app

THIS_DIR = Path(__file__).parent.resolve()


def pytest_addoption(parser):
    parser.addoption(
        '--reuse-db', action='store_true', default=False, help='keep the existing database if it exists'
    )


@pytest.fixture(scope='session')
def full_scope_settings():
    return Settings(
        auth_bcrypt_work_factor=5,  # make tests faster
        auth_local_domains={'example.com'},
        easy_login_attempts=4,
        client_ip_header=None,
        secure_cookies=False,
        pg_main_name='em2_test',
        pg_auth_name='em2_auth_test',
        auth_server_url='http://auth.example.com',
        auth_server_sys_url='http://auth.example.com',
        EXTERNAL_DOMAIN='em2.platform.example.com',
        ORIGIN_DOMAIN='https://frontend.example.com',
        authenticator_cls='tests.fixture_classes.SimpleAuthenticator',
        db_cls='tests.fixture_classes.TestDatabase',
        pusher_cls='tests.fixture_classes.DNSMockedPusher',
        fallback_cls='tests.fixture_classes.TestFallbackHandler',
        PRIVATE_DOMAIN_KEY_FILE=str(THIS_DIR / 'fixture_classes/keys/private.pem'),
        COMMS_PROTO='http',
    )


@pytest.fixture
async def _foreign_server(loop, aiohttp_server):
    app = create_test_app()
    return await aiohttp_server(app)


@pytest.fixture
def settings(full_scope_settings, _foreign_server):
    return full_scope_settings.copy(update={'auth_server_sys_url': f'http://localhost:{_foreign_server.port}'})


@pytest.fixture(scope='session')
def clean_db(request, full_scope_settings):
    # loop fixture has function scope so can't be used here.
    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(full_scope_settings, not request.config.getoption('--reuse-db')))
    teardown_test_loop(loop)


@pytest.yield_fixture
async def db_conn(loop, settings, clean_db, redis):
    conn = await asyncpg.connect(dsn=settings.pg_dsn)

    tr = conn.transaction()
    await tr.start()

    yield conn

    await tr.rollback()
    await conn.close()


@pytest.fixture(scope='session')
def full_scope_auth_settings(full_scope_settings):
    return full_scope_settings.copy(update={'mode': 'auth'})


@pytest.fixture
def auth_settings(full_scope_auth_settings):
    return full_scope_auth_settings.copy()


@pytest.fixture(scope='session')
def auth_clean_db(request, full_scope_auth_settings):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(full_scope_auth_settings, not request.config.getoption('--reuse-db')))
    teardown_test_loop(loop)


@pytest.yield_fixture
async def auth_db_conn(loop, auth_settings, auth_clean_db):
    conn = await asyncpg.connect(dsn=auth_settings.pg_dsn)

    tr = conn.transaction()
    await tr.start()

    yield conn

    await tr.rollback()
    await conn.close()


def _to_str(v):
    if isinstance(v, Enum):
        return v.value
    else:
        return str(v)


@pytest.fixture
def url(request):
    client = request.getfixturevalue('cli')

    def _url(name, **parts):
        query = parts.pop('query', None)
        parts = {k: _to_str(v) for k, v in parts.items()}
        return client.server.app.router[name].url_for(**parts).with_query(query)
    return _url


@pytest.fixture
def foreign_server(_foreign_server, cli):
    cli.server.app['pusher'].set_foreign_port(_foreign_server.port)
    return _foreign_server


class ConvInfo(NamedTuple):
    id: int
    key: str
    first_msg_key: str
    creator_address: str


@pytest.fixture
def create_conv(db_conn):
    async def create_conv_(*, creator='testing@example.com', key='key12345678',
                           subject='Test Conversation', published=False, recipient=None):
        creator_recip_id = await get_create_recipient(db_conn, creator)
        args = key, creator_recip_id, subject, published
        conv_id = await db_conn.fetchval('INSERT INTO conversations (key, creator, subject, published) '
                                         'VALUES ($1, $2, $3, $4) RETURNING id', *args)
        await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, creator_recip_id)
        first_msg_key = 'msg-firstmessagekeyx'
        args = first_msg_key, conv_id, 'this is the message'
        await db_conn.execute('INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)', *args)
        if recipient:
            r_id = await get_create_recipient(db_conn, recipient)
            await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, r_id)

        if published:
            await db_conn.execute("""
                INSERT INTO actions (key, conv, actor, verb, message)
                SELECT 'pub-add-message-1234', $1, $2, 'publish', m.id
                FROM messages as m
                WHERE m.conv = $1
                LIMIT 1
                """, conv_id, creator_recip_id)

        return ConvInfo(id=conv_id, key=key, first_msg_key=first_msg_key, creator_address=creator)
    return create_conv_


@pytest.yield_fixture
async def redis(loop, settings):
    redis = await create_redis(('localhost', 6379), db=settings.R_DATABASE)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


@pytest.yield_fixture
async def auth_redis(loop, auth_settings):
    redis = await create_redis(('localhost', 6379), db=auth_settings.AUTH_R_DATABASE)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


async def startup_modify_app(app):
    app['db'].conn = app['_conn']
    app['pusher']._concurrency_enabled = False
    await app['pusher'].startup()
    app['pusher'].db.conn = app['_conn']


async def shutdown_modify_app(app):
    await app['pusher'].session.close()


class CloseToNow:
    """
    these all need `pytest_assertrepr_compare` adding and moving to pytest-toolbox
    """
    def __init__(self, delta=2):
        self.delta: float = delta
        self.now = datetime.utcnow()
        self.match = False
        self.other = None

    def __eq__(self, other):
        self.other = other
        if not isinstance(other, datetime):
            other = parse_datetime(other)
        if other.tzinfo:
            self.now = self.now.replace(tzinfo=timezone.utc)
        self.match = -self.delta < (self.now - other).total_seconds() < self.delta
        return self.match

    def __repr__(self):
        if self.match:
            # if we've got the correct value return it to aid in diffs
            return repr(self.other)
        else:
            # else return something which explains what's going on.
            return f'<CloseToNow(delta={self.delta})>'


class AnyInt:
    def __init__(self):
        self.v = None

    def __eq__(self, other):
        if type(other) == int:
            self.v = other
            return True

    def __repr__(self):
        if self.v is None:
            return '<AnyInt>'
        else:
            return repr(self.v)


class RegexStr:
    re = re

    def __init__(self, regex, flags=re.S):
        self._regex = re.compile(regex, flags=flags)
        self.v = None

    def __eq__(self, other):
        if self._regex.fullmatch(other):
            self.v = other
            return True
        return False

    def __repr__(self):
        if self.v is None:
            return f'<RegexStr(regex={self._regex!r}>'
        else:
            return repr(self.v)


class IsUUID:
    def __init__(self):
        self.v = None

    def __eq__(self, other):
        if isinstance(other, UUID):
            self.v = other
            return True
        # could also check for regex

    def __repr__(self):
        return repr(self.v) if self.v else 'UUID(*)'
