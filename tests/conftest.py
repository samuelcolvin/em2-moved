import pytest

from em2 import Settings
from em2.foreign import create_foreign_app as _create_foreign_app


def create_test_app(*args):
    settings = Settings(
        LOCAL_DOMAIN='testapp.com',
        authenticator_cls='tests.fixture_classes.FixedSimpleAuthenticator',
    )
    return _create_foreign_app(settings)


@pytest.yield_fixture
def client(loop, test_client):
    test_client = loop.run_until_complete(test_client(create_test_app))
    yield test_client
    loop.run_until_complete(test_client.server.app.shutdown())
    loop.run_until_complete(test_client.server.app.cleanup())
