import logging

import aiodns
from aiodns.error import DNSError
from arq import Actor
from arq.jobs import DatetimeJob

dns_logger = logging.getLogger('em2.dns')


class RedisDNSMixin(Actor):
    job_class = DatetimeJob

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._resolver = None

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self.loop)
        return self._resolver

    async def mx_query(self, host):
        try:
            results = await self.resolver.query(host, 'MX')
        except (DNSError, ValueError) as e:
            dns_logger.warning('MX query error on %s, %s: %s', host, e.__class__.__name, e)
            return []
        else:
            print(results)
            results = [(r.priority, r.host) for r in results]
            results.sort()
            return results


class RedisMethods(RedisDNSMixin):
    _dft_value = b'1'

    async def set_exat(self, redis, key: bytes, value: str, expires_at: int):
        pipe = redis.pipeline()
        pipe.set(key, value)
        pipe.expireat(key, expires_at)
        await pipe.execute()

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return bool(await redis.exists(platform_token.encode()))

    async def get_value(self, key: str):
        async with await self.get_redis_conn() as redis:
            return await redis.get(key.encode())
