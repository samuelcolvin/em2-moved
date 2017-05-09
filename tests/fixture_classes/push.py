import re
from copy import deepcopy

from aiohttp.test_utils import TestClient
from arq.testing import MockRedisMixin

from em2 import Settings, create_app
from em2.comms import Pusher
from em2.comms.web.push import WebDNSPusher
from tests.conftest import test_store

from .authenicator import MockDNSResolver


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


class SimpleMockRedisPusher(MockRedisMixin, SimplePusher):
    pass


class CustomTestClient(TestClient):
    def __init__(self, loop, app, domain):
        self.domain = domain
        self.regex = re.compile(r'https://em2\.{}(/.*)'.format(self.domain))
        super().__init__(app, loop=loop)

    def make_url(self, path):
        m = self.regex.match(path)
        assert m, (path, self.regex)
        sub_path = m.groups()[0]
        return self._server.make_url(sub_path)


def create_test_app(domain='testapp.com'):
    settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        LOCAL_DOMAIN=domain,
        AUTHENTICATOR_CLS='tests.fixture_classes.FixedSimpleAuthenticator',
    )
    return create_app(settings=settings)


class WebMockedDNSPusher(WebDNSPusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0

    @property
    def resolver(self):
        return MockDNSResolver()

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)


class DoubleMockPusher(WebMockedDNSPusher):
    """
    WebDNSPusher with both dns and http mocked
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_client = None
        self.session = None

    async def create_test_client(self, remote_domain='platform.remote.com'):
        self.session and await self.session.close()
        self.app = create_test_app(remote_domain)
        self.test_client = CustomTestClient(self.loop, self.app, remote_domain)
        await self.test_client.start_server()
        self.session = self.test_client

    def _now_unix(self):
        return 2461449600
