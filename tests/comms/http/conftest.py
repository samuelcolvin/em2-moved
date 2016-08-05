import pytest

from em2.core import Controller
from em2.comms.http import create_app
from tests.fixture_classes import SimpleDataStore, SimpleAuthenticator

pytest_plugins = 'aiohttp.pytest_plugin'


def _create_app(loop):
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: 2461449600
    return create_app(ctrl, auth, loop=loop)


@pytest.fixture
def client(loop, test_client):
    test_client = loop.run_until_complete(test_client(_create_app))
    test_client.em2_ctrl = test_client.app['controller']
    return test_client
