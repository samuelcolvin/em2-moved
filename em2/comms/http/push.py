import json

import aiohttp
from em2.comms.push import AsyncRedisPusher
from em2.exceptions import FailedOutboundAuthentication, Em2ConnectionError

JSON_HEADER = {'content-type': 'application/json'}


class HttpDNSPusher(AsyncRedisPusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if not self._session:
            self._session = aiohttp.ClientSession(loop=self.loop)
        return self._session

    async def get_node(self, conv, domain, *addresses):
        cache_key = 'nd:{}:{}'.format(conv, domain).encode()
        async with await self.get_redis_conn() as redis:
            node = await redis.get(cache_key)
            if node:
                return node
            results = await self.resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
            for _, host in results:
                node = None
                if host == self._settings.LOCAL_DOMAIN:
                    node = self.LOCAL
                elif host.startswith('em2.'):
                    try:
                        await self.authenticate(host)
                    except Em2ConnectionError:
                        # connection failed domain is probably not em2
                        pass
                    else:
                        # TODO query host to find associated node
                        node = host
                if node:
                    await redis.setex(cache_key, self._settings.COMMS_DOMAIN_CACHE_TIMEOUT, host.encode())
                    return node
        # TODO SMTP fallback
        raise NotImplementedError()

    async def _authenticate_direct(self, domain, data):
        url = domain + '/authenticate'
        if not url.startswith('em2.'):
            url = 'em2.' + url
        # TODO more error checks
        try:
            async with self.session.post(url, data=json.dumps(data), headers=JSON_HEADER) as r:
                t = await r.text()
                if r.status != 201:
                    raise FailedOutboundAuthentication('{} response {} != 201, response: {}'.format(url, r.status, t))
        except aiohttp.ClientOSError as e:
            # generally "could not resolve host" or "connection refused"
            raise ConnectionError('conn count connect to "{}"'.format(url)) from e
        data = json.loads(t)
        return data['key']

    async def close(self):
        if self._session:
            await self._session.close()
        await super().close()
