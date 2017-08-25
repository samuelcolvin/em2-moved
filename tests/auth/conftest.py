import pytest
from cryptography.fernet import Fernet

from em2.auth import create_auth_app
from em2.utils.encoding import msg_encode


async def startup_modify_app(app):
    app['db'].conn = app['_conn']


@pytest.fixture
def cli(loop, auth_settings, auth_db_conn, test_client):
    app = create_auth_app(auth_settings)
    app['_conn'] = auth_db_conn
    app.on_startup.append(startup_modify_app)
    return loop.run_until_complete(test_client(app))


@pytest.fixture
def token(settings):
    def _token(address='testing@example.com', **kwargs):
        fernet = Fernet(settings.auth_token_key)
        data = msg_encode(dict(address=address, **kwargs))
        return fernet.encrypt(data).decode()
    return _token
