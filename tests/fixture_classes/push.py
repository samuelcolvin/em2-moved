import socket

from aiohttp import AsyncResolver

from em2.push import Pusher

from .dns_resolver import MockDNSResolver


class DNSMockedPusher(Pusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0
        self.settings = self.settings.copy()
        self.dns = MockDNSResolver(self.settings, self.loop)

    @classmethod
    def _get_http_resolver(cls):
        return MockAsyncResolver()

    def set_foreign_port(self, port):
        self.settings.EXTERNAL_DOMAIN += f':{port}'
        self.dns._port = port
        self.session.connector._resolver.mock_resolve_port = port


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
