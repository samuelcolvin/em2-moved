import pytest
from cryptography.fernet import Fernet

from em2.domestic import create_domestic_app
from em2.utils.encoding import msg_encode

from ..conftest import shutdown_modify_app, startup_modify_app

test_addr = 'testing@example.com'


@pytest.fixture
def cli(loop, settings, db_conn, test_client, redis):
    data = {
        'address': test_addr,
        'token': '123',
    }
    data = msg_encode(data)
    fernet = Fernet(settings.SECRET_SESSION_KEY)
    cookies = {
        settings.cookie_name: fernet.encrypt(data).decode()
    }
    app = create_domestic_app(settings, 'd-testing')
    app['_conn'] = db_conn
    app.on_startup.append(startup_modify_app)
    app.on_shutdown.append(shutdown_modify_app)
    return loop.run_until_complete(test_client(app, cookies=cookies))


@pytest.fixture
def conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator=test_addr))
