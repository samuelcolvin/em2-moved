import base64

import pytest
from cryptography.fernet import Fernet

from em2 import Settings
from em2.cli.database import prepare_database
from em2.domestic import create_domestic_app as _create_domestic_app
from em2.foreign import create_foreign_app as _create_foreign_app
from em2.utils.encoding import msg_encode


@pytest.fixture(scope='session')
def settings():
    return Settings(
        PG_NAME='em2_test',
        PG_POOL_MAXSIZE=4,
        PG_POOL_TIMEOUT=5,
        LOCAL_DOMAIN='testapp.com',
        authenticator_cls='tests.fixture_classes.FixedSimpleAuthenticator',
    )


@pytest.fixture
def fclient(loop, settings, test_client):
    app = _create_foreign_app(settings)
    return loop.run_until_complete(test_client(app))


@pytest.fixture
def dclient(loop, settings, test_client):
    data = {
        'address': 'testing@example.com'
    }
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(settings.SECRET_KEY))
    cookies = {
        settings.COOKIE_NAME: fernet.encrypt(data).decode()
    }
    app = _create_domestic_app(settings)
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


@pytest.fixture
def clean_db(loop, settings):
    loop.run_until_complete(prepare_database(settings, True))
