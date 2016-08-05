import re

import pytest
from aiohttp.test_utils import TestClient

from em2 import Settings
from em2.core import Controller
from em2.comms.http import create_app
from tests.fixture_classes import SimpleDataStore, SimpleAuthenticator
from tests.fixture_classes.authenicator import get_private_key
from tests.fixture_classes.push import HttpMockedDNSPusher

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


class CustomTestClient(TestClient):
    def __init__(self, app, domain, protocol='http'):
        self.domain = domain
        self.regex = re.compile('^em2\.{}(/.*)$'.format(self.domain))
        super().__init__(app, protocol)

    def request(self, method, path, *args, **kwargs):
        m = self.regex.search(path)
        assert m, (path, self.regex)
        sub_path = m.groups()[0]
        return self._session.request(method, self._root + sub_path, *args, **kwargs)


@pytest.yield_fixture
def domain_pusher(loop):
    pusher = client = None
    settings = Settings(R_DATABASE=2, LOCAL_DOMAIN='local.com', PRIVATE_DOMAIN_KEY=get_private_key())

    async def _create_domain_client_app(domain='example.com'):
        nonlocal client, pusher
        app = _create_app(loop)
        client = CustomTestClient(app, domain)
        await client.start_server()

        pusher = HttpMockedDNSPusher(settings=settings, loop=loop)
        pusher._now_unix = lambda: 2461449600
        async with await pusher.get_redis_conn() as redis:
            await redis.flushdb()
        pusher._session = client
        return pusher

    yield _create_domain_client_app

    if client:
        client.close()
        pusher._session = None
        loop.run_until_complete(pusher.close())
