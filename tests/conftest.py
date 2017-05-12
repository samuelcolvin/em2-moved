import asyncio
import base64

import asyncpg
import pytest
from cryptography.fernet import Fernet

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
    app['db'].conn = app['conn']


@pytest.fixture
def fclient(loop, settings, db_conn, test_client):
    app = create_foreign_app(settings)
    app['conn'] = db_conn
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
    app = create_domestic_app(settings)
    app['conn'] = db_conn
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
    hash = 'hash123'
    args = hash, recipient_id, 'Test Conversation', 'test-conv'
    conv_id = await db_conn.fetchval('INSERT INTO conversations (hash, creator, subject, ref) '
                                     'VALUES ($1, $2, $3, $4) RETURNING id', *args)
    await db_conn.execute('INSERT INTO participants (conversation, recipient) VALUES ($1, $2)', conv_id, recipient_id)
    args = 'testkey_length16', conv_id, 'this is the message'
    await db_conn.execute('INSERT INTO messages (key, conversation, body) VALUES ($1, $2, $3)', *args)
    return hash


@pytest.fixture
def conv_hash(loop, db_conn):
    return loop.run_until_complete(create_conversation(db_conn))
