import base64

import pytest
from cryptography.fernet import Fernet

from em2.domestic import create_domestic_app
from em2.utils.encoding import msg_encode

from ..conftest import create_conversation
from ..fixture_classes.foreign_server import create_test_app

test_addr = 'testing@example.com'


async def d_startup_modify_app(app):
    app['db'].conn = app['_conn']
    app['pusher']._concurrency_enabled = False
    await  app['pusher'].startup()
    app['pusher'].db.conn = app['_conn']


async def d_shutdown_modify_app(app):
    await app['pusher'].session.close()


@pytest.fixture
def cli(loop, settings, db_conn, test_client):
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
    app.on_startup.append(d_startup_modify_app)
    app.on_shutdown.append(d_shutdown_modify_app)
    return loop.run_until_complete(test_client(app, cookies=cookies))


@pytest.fixture
def conv(loop, db_conn):
    return loop.run_until_complete(create_conversation(db_conn, test_addr))


@pytest.fixture
def foreign_server(loop, test_server, cli):
    app = create_test_app(loop)
    server = loop.run_until_complete(test_server(app))
    cli.server.app['pusher'].set_foreign_port(server.port)
    return server
