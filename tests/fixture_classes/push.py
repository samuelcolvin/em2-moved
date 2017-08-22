import socket

from aiohttp import AsyncResolver

from em2.push import Pusher

from .auth import MockDNSResolver


class DNSMockedPusher(Pusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0
        self._foreign_port = None
        self.settings = self.settings.copy()

    @property
    def resolver(self):
        return MockDNSResolver(self._foreign_port)

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)

    @classmethod
    def _get_http_resolver(cls):
        return MockAsyncResolver()

    def set_foreign_port(self, port):
        self._foreign_port = port
        self.settings.FOREIGN_DOMAIN += f':{port}'
        self.session.connector._resolver.mock_resolve_port = port


class NullPusher(Pusher):
    async def push(self, action, data):
        pass

    async def get_node(self, domain):
        pass

    async def authenticate(self, node_domain: str):
        pass


class MockAsyncResolver(AsyncResolver):
    mock_resolve_port = None

    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [{
            'hostname': host,
            'host': '127.0.0.1',
            'port': self.mock_resolve_port,
            'family': family,
            'proto': 0,
            'flags': socket.AI_NUMERICHOST,
        }]
