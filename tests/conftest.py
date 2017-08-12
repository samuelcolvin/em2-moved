import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import asyncpg
import pytest
from aioredis import create_redis
from pydantic.datetime_parse import parse_datetime

from em2 import Settings
from em2.cli.database import prepare_database

THIS_DIR = Path(__file__).parent.resolve()


@pytest.fixture(scope='session')
def settings():
    return Settings(
        PG_NAME='em2_test',
        LOCAL_DOMAIN='em2.platform.example.com',
        authenticator_cls='tests.fixture_classes.FixedSimpleAuthenticator',
        db_cls='tests.fixture_classes.TestDatabase',
        pusher_cls='tests.fixture_classes.DNSMockedPusher',
        PRIVATE_DOMAIN_KEY_FILE=str(THIS_DIR / 'fixture_classes/keys/private.pem'),
        COMMS_SCHEMA='http',
    )


@pytest.fixture(scope='session')
def clean_db(settings):
    # loop fixture has function scope so can't be used here.
    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(settings, True))


@pytest.yield_fixture
def db_conn(loop, settings, clean_db):
    await_ = loop.run_until_complete
    conn = await_(asyncpg.connect(dsn=settings.pg_dsn, loop=loop))

    tr = conn.transaction()
    await_(tr.start())

    yield conn

    await_(tr.rollback())


@pytest.fixture
def url(request):
    client = request.getfixturevalue('cli')

    def _url(name, **parts):
        return client.server.app.router[name].url_for(**parts)
    return _url


class ConvInfo(NamedTuple):
    id: int
    key: str
    first_msg_key: str
    creator_address: str


async def create_conversation(db_conn, creator):
    recipient_id = await db_conn.fetchval('INSERT INTO recipients (address) VALUES ($1) RETURNING id', creator)
    key = 'key123'
    args = key, recipient_id, 'Test Conversation', 'test-conv'
    conv_id = await db_conn.fetchval('INSERT INTO conversations (key, creator, subject, ref) '
                                     'VALUES ($1, $2, $3, $4) RETURNING id', *args)
    await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, recipient_id)
    first_msg_key = 'msg-firstmessagekeyx'
    args = first_msg_key, conv_id, 'this is the message'
    await db_conn.execute('INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)', *args)
    return ConvInfo(id=conv_id, key=key, first_msg_key=first_msg_key, creator_address=creator)


@pytest.yield_fixture
def redis(loop):
    async def _redis():
        redis = await create_redis(('localhost', 6379))
        await redis.flushdb()
        return redis

    redis = loop.run_until_complete(_redis())

    yield redis

    redis.close()
    loop.run_until_complete(redis.wait_closed())


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
        if isinstance(other, str):
            other = parse_datetime(other)
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
    def __init__(self, regex):
        self._regex = re.compile(regex)
        self.v = None

    def __eq__(self, other):
        if self._regex.fullmatch(other):
            self.v = other
            return True

    def __repr__(self):
        if self.v is None:
            return f'<RegexStr(regex={self._regex!r}>'
        else:
            return repr(self.v)


timstamp_regex = RegexStr(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:.\d{1,6})?')


CHANGES = [
    ('"', "'"),
    (' false', ' False'),
    (' true', ' True'),
    (' null', ' None'),
]


def python_dict(v):
    s = json.dumps(v, indent=4, sort_keys=True)
    for pattern, repl in CHANGES:
        s = s.replace(pattern, repl)
    return s
