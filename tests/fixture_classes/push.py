import re
from copy import deepcopy

from aiohttp.test_utils import TestClient

from em2 import Settings
from em2.comms import Pusher
from em2.comms.http import create_app
from em2.comms.http.push import HttpDNSPusher
from em2.core import Controller
from tests.conftest import test_store

from .authenicator import MockDNSResolver, SimpleAuthenticator


class Network:
    def __init__(self):
        self.nodes = {}

    def add_node(self, domain, controller):
        assert domain not in self.nodes
        self.nodes[domain] = controller


class SimplePusher(Pusher):
    def __init__(self, *args, **kwargs):
        kwargs['concurrency_enabled'] = False
        super().__init__(*args, **kwargs)
        self.network = Network()

    async def startup(self):
        await super().startup()
        self.ds.data = test_store(self.settings.LOCAL_DOMAIN)

    async def _push_em2(self, nodes, action, data):
        prop_data = deepcopy(data)
        for d in nodes:
            ctrl = self.network.nodes[d]
            if ctrl != self.LOCAL:
                await ctrl.act(action, **prop_data)

    async def get_node(self, domain):
        return self.LOCAL if domain == self.settings.LOCAL_DOMAIN else domain

    async def _authenticate_direct(self, node_domain):
        raise NotImplemented()


class CustomTestClient(TestClient):
    def __init__(self, app, domain):
        self.domain = domain
        self.regex = re.compile(r'https://em2\.{}(/.*)'.format(self.domain))
        super().__init__(app)

    def make_url(self, path):
        m = self.regex.match(path)
        assert m, (path, self.regex)
        sub_path = m.groups()[0]
        return self._server.make_url(sub_path)


def create_test_app(loop, domain='testapp.com'):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore', LOCAL_DOMAIN=domain)
    ctrl = Controller(settings, loop=loop)
    auth = SimpleAuthenticator(settings=settings)
    auth._now_unix = lambda: 2461449600
    return create_app(ctrl, auth, loop=loop)


class HttpMockedDNSPusher(HttpDNSPusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0

    @property
    def resolver(self):
        return MockDNSResolver()

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)


class DoubleMockPusher(HttpMockedDNSPusher):
    """
    HttpDNSPusher with both dns and http mocked
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_client = None
        self.session = None

    async def create_test_client(self, remote_domain='platform.remote.com'):
        self.app = create_test_app(self.loop, remote_domain)
        self.test_client = CustomTestClient(self.app, remote_domain)
        await self.test_client.start_server()
        self.session = self.test_client

    def _now_unix(self):
        return 2461449600
