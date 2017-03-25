import asyncio
import logging

import aiodns
from aiodns.error import DNSError
from arq import Actor
from arq.jobs import DatetimeJob
from async_timeout import timeout

dns_logger = logging.getLogger('em2.dns')


class RedisDNSActor(Actor):
    job_class = DatetimeJob
    _dft_value = b'1'

    def __init__(self, **kwargs):
        self.redis_settings = self.settings.redis
        super().__init__(**kwargs)
        self._resolver = None

    @property
    def resolver(self):
        if self._resolver is None:
            nameservers = [self.settings.COMMS_DNS_IP] if self.settings.COMMS_DNS_IP else None
            self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=nameservers)
        return self._resolver

    async def mx_query(self, host):
        results = await self.dns_query(host, 'MX')
        results = [(r.priority, r.host) for r in results]
        results.sort()
        return results

    async def dns_query(self, host, qtype):
        try:
            with timeout(5, loop=self.loop):
                return await self.resolver.query(host, qtype)
        except (DNSError, ValueError, asyncio.TimeoutError) as e:
            dns_logger.warning('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []

    async def set_exat(self, redis, key: bytes, value: str, expires_at: int):
        pipe = redis.pipeline()
        pipe.set(key, value)
        pipe.expireat(key, expires_at)
        await pipe.execute()

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return bool(await redis.exists(platform_token.encode()))
