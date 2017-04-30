import base64

import pytest
from cryptography.fernet import Fernet

from em2 import Settings
from em2.core import Action, Verbs
from em2.utils import msg_encode
from tests.fixture_classes.push import create_test_app


@pytest.fixture
def client(loop, test_client, reset_store):
    settings = Settings()
    data = {
        'address': 'testing@example.com'
    }
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(settings.SECRET_KEY))
    cookies = {
        settings.COOKIE_NAME: fernet.encrypt(data).decode()
    }
    return loop.run_until_complete(test_client(create_test_app(), cookies=cookies))


@pytest.fixture
def conv_id(loop, client):
    ctrl = client.server.app['controller']
    action = Action('testing@example.com', None, Verbs.ADD)
    return loop.run_until_complete(
        ctrl.act(action, subject='foo bar', body='hello')
    )


@pytest.fixture
def url(client):
    def _url(name, **parts):
        return client.server.app['uiapp'].router[name].url_for(**parts)
    return _url
