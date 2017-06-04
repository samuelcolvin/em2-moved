import asyncio
import base64
import json
import re
from datetime import datetime

import asyncpg
import pytest
from aioredis import create_redis
from cryptography.fernet import Fernet
from pydantic.datetime_parse import parse_datetime

from em2 import Settings
from em2.cli.database import prepare_database
from em2.domestic import create_domestic_app
from em2.foreign import create_foreign_app
from em2.utils.encoding import msg_encode


@pytest.fixture(scope='session')
def settings():
    return Settings(
        PG_NAME='em2_test',
        LOCAL_DOMAIN='testapp.com',
        authenticator_cls='tests.fixture_classes.FixedSimpleAuthenticator',
        db_cls='tests.fixture_classes.TestDatabase',
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


def _set_connection(app):
    app['db'].conn = app['_conn']


@pytest.fixture
def fclient(loop, settings, db_conn, test_client):
    app = create_foreign_app(settings)
    app['_conn'] = db_conn
    app.on_startup.append(_set_connection)
    return loop.run_until_complete(test_client(app))


test_addr = 'testing@example.com'


@pytest.fixture
def dclient(loop, settings, db_conn, test_client):
    data = {
        'address': test_addr
    }
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(settings.SECRET_KEY))
    cookies = {
        settings.COOKIE_NAME: fernet.encrypt(data).decode()
    }
    app = create_domestic_app(settings, 'd-testing')
    app['_conn'] = db_conn
    app.on_startup.append(_set_connection)
    return loop.run_until_complete(test_client(app, cookies=cookies))


@pytest.fixture
def url(request):
    if 'fclient' in request.fixturenames:
        client_name = 'fclient'
    elif 'dclient' in request.fixturenames:
        client_name = 'dclient'
    else:
        raise NotImplementedError()
    client = request.getfixturevalue(client_name)

    def _url(name, **parts):
        return client.server.app.router[name].url_for(**parts)
    return _url


async def create_conversation(db_conn):
    recipient_id = await db_conn.fetchval('INSERT INTO recipients (address) VALUES ($1) RETURNING id', test_addr)
    key = 'key123'
    args = key, recipient_id, 'Test Conversation', 'test-conv'
    conv_id = await db_conn.fetchval('INSERT INTO conversations (key, creator, subject, ref) '
                                     'VALUES ($1, $2, $3, $4) RETURNING id', *args)
    await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, recipient_id)
    args = 'msg-firstmessage_key', conv_id, 'this is the message'
    await db_conn.execute('INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)', *args)
    return key


@pytest.fixture
def conv_key(loop, db_conn):
    return loop.run_until_complete(create_conversation(db_conn))


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
