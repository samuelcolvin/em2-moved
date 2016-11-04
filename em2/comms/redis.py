import aiodns
from arq import Actor


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
