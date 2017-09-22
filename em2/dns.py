import asyncio
import logging

import aiodns
from aiodns.error import DNSError
from async_timeout import timeout

from . import Settings

logger = logging.getLogger('em2.dns')


class DNSResolver:
    def __init__(self, settings: Settings, loop):
        self.settings = settings
        self.loop = loop
        self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=self.settings.COMMS_DNS_IPS)

    async def mx_hosts(self, host):
        results = await self.query(host, 'MX')
        results = [(r.priority, r.host) for r in results]
        results.sort()
        for _, host in results:
            yield host

    async def domain_is_local(self, domain: str) -> bool:
        # results could be cached
        async for host in self.mx_hosts(domain):
            if host == self.settings.EXTERNAL_DOMAIN:
                return True
        return False

    async def query(self, host, qtype):
        try:
            with timeout(5, loop=self.loop):
                return await self._resolver.query(host, qtype)
        except (DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.debug('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []
