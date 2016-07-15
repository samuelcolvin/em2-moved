import aiodns
import aioredis

from em2.core.utils import BaseServiceCls
from em2.exceptions import Em2Exception


class RedisDNSMixin(BaseServiceCls):
    _resolver = None
    _redis_pool = None
    _dft_value = '1'

    async def init(self):
        if self._redis_pool is not None:
            raise Em2Exception('redis pool already initialised')
        address = self._settings.REDIS_HOST, self._settings.REDIS_PORT
        self._redis_pool = await aioredis.create_pool(address, db=self._settings.REDIS_DATABASE,
                                                      encoding='utf8', loop=self._loop)

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self._loop)
        return self._resolver
