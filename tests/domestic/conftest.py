import base64

import pytest
from cryptography.fernet import Fernet

from em2.domestic import create_domestic_app
from em2.utils.encoding import msg_encode

from ..conftest import create_conversation, shutdown_modify_app, startup_modify_app

test_addr = 'testing@example.com'


@pytest.fixture
def cli(loop, settings, db_conn, test_client, redis):
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
    app.on_startup.append(startup_modify_app)
    app.on_shutdown.append(shutdown_modify_app)
    return loop.run_until_complete(test_client(app, cookies=cookies))


@pytest.fixture
def conv(loop, db_conn):
    return loop.run_until_complete(create_conversation(db_conn, test_addr))
