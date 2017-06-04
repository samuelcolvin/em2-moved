from em2.push import Pusher

from .authenicator import MockDNSResolver


class DNSMockedPusher(Pusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0

    @property
    def resolver(self):
        return MockDNSResolver()

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)


class NullPusher(Pusher):
    async def push(self, action, data):
        pass

    async def get_node(self, domain):
        pass

    async def authenticate(self, node_domain: str):
        pass
