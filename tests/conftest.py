import pytest

from em2 import Settings
from em2.foreign import create_foreign_app as _create_foreign_app


def create_test_app(*args):
    settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        LOCAL_DOMAIN='testapp.com',
        AUTHENTICATOR_CLS='tests.fixture_classes.FixedSimpleAuthenticator',
    )
    return _create_foreign_app(settings)


@pytest.yield_fixture
def client(loop, test_client):
    test_client = loop.run_until_complete(test_client(create_test_app))
    yield test_client
    loop.run_until_complete(test_client.server.app.shutdown())
    loop.run_until_complete(test_client.server.app.cleanup())
