import aiodns

from arq import Actor

DEFAULT_VALUE = b'1'


class RedisDNSMixin(Actor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._resolver = None

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self.loop)
        return self._resolver


class RedisMethods(RedisDNSMixin):
    async def store_value(self, key: str, expiresat: int, value: str=DEFAULT_VALUE):
        async with await self.get_redis_conn() as redis:
            pipe = redis.pipeline()
            b_key = key.encode()
            pipe.set(b_key, value)
            pipe.expireat(b_key, expiresat)
            await pipe.execute()

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return await redis.exists(platform_token.encode())

    async def get_value(self, key: str):
        async with await self.get_redis_conn() as redis:
            return await redis.get(key.encode())
