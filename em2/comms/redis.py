import aiodns
import aioredis

from arq import Actor

from em2.utils import BaseServiceCls


class RedisDNSMixin(BaseServiceCls, Actor):
    _resolver = None
    _dft_value = b'1'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._redis_pool = None

    async def create_redis_pool(self):
        address = self._settings.REDIS_HOST, self._settings.REDIS_PORT
        return await aioredis.create_pool(address, loop=self.loop, db=self._settings.REDIS_DATABASE)

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self.loop)
        return self._resolver
