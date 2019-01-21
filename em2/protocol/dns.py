import asyncio
import logging

import aiodns
from async_timeout import timeout

from .. import Settings

logger = logging.getLogger('em2.dns')


class DNSResolver:
    def __init__(self, settings: Settings, loop):
        self.settings = settings
        self.loop = loop
        self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=self.settings.COMMS_DNS_IPS)

    async def mx_hosts(self, host):
        results = await self.query(host, 'MX')
        for _, host in sorted((r.priority, r.host) for r in results):
            yield host

    async def domain_is_local(self, domain: str) -> bool:
        # results could be cached
        async for host in self.mx_hosts(domain):
            if host == self.settings.EXTERNAL_DOMAIN:
                return True
        return False

    async def is_em2_node(self, host):
        # see if any of the hosts TXT records start with with the prefix for em2 public keys
        dns_results = await self.query(host, 'TXT')
        return any(r.text.decode().startswith('v=em2key') for r in dns_results)

    async def query(self, host, qtype):
        # could use an lru & ttl cache
        try:
            with timeout(5, loop=self.loop):
                return await self._resolver.query(host, qtype)
        except (aiodns.error.DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.debug('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []
