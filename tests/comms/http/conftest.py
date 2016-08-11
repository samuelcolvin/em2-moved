import re

import pytest
from aiohttp.test_utils import TestClient

from em2 import Settings
from em2.comms.http import create_app
from em2.core import Controller
from tests.fixture_classes import SimpleAuthenticator, SimpleDataStore
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


class DoubleMockPusher(HttpMockedDNSPusher):
    """
    HttpDNSPusher with both dns and http mocked
    """
    def __init__(self, *, settings=None, **kwargs):
        settings = Settings(R_DATABASE=2, LOCAL_DOMAIN='em2.local.com', PRIVATE_DOMAIN_KEY=get_private_key())
        self.test_client = None
        super().__init__(settings=settings, **kwargs)

    async def create_session(self):
        self.app = _create_app(self.loop)
        self.test_client = CustomTestClient(self.app, 'platform.remote.com')
        await self.test_client.start_server()

    @property
    def session(self):
        if not self.test_client:
            raise RuntimeError('session must be initialised with create_session before accessing session')
        return self.test_client

    def _now_unix(self):
        return 2461449600


@pytest.yield_fixture
def pusher(loop):
    async def _create_pusher():
        p = DoubleMockPusher(loop=loop)
        await p.create_session()
        async with await p.get_redis_conn() as redis:
            await redis.flushdb()
        return p
    _pusher = loop.run_until_complete(_create_pusher())

    yield _pusher

    _pusher.test_client.close()
    loop.run_until_complete(_pusher.close())
