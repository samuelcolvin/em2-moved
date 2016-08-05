import json

import aiohttp
from em2.comms.push import AsyncRedisPusher
from em2.exceptions import FailedOutboundAuthentication


class HttpDNSPusher(AsyncRedisPusher):
    json_headers = {'content-type': 'application/json'}

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
            for _, platform in results:
                if platform == self._settings.LOCAL_DOMAIN:
                    node = self.LOCAL
                else:
                    node = await self.try_node(conv, domain, addresses)
                    if node == self._settings.LOCAL_DOMAIN:
                        node = self.LOCAL
                if node:
                    await redis.setex(cache_key, self._settings.COMMS_DOMAIN_CACHE_TIMEOUT, platform.encode())
                    return node
        # TODO SMTP fallback
        raise NotImplementedError()

    async def _authenticate_direct(self, domain, data):
        url = 'em2.{}/authenticate'.format(domain)
        async with self.session.post(url, data=json.dumps(data)) as r:
            t = await r.text()
            if r.status != 201:
                raise FailedOutboundAuthentication('{} response {} != 201, response: {}'.format(url, r.status, t))
        # TODO error checks
        data = json.loads(t)
        return data['key']

    async def try_node(self, conv, platform_domain, addresses):
        url = 'em2.{}/lookup/{}'.format(platform_domain, conv)
        # TODO error checking
        r = await self.session.head(url, allow_redirects=False)
        r.close()

        if not (r.status in {200, 204, 303} or r.headers.get('em2')):
            # em2 is not running on the domain, most likely an SMTP address
            return False
        if r.status == 200:
            # the current url should be used as the conversation node
            return url
        if r.status == 303:
            # the platform knows what node to use and added it to the "Location" header
            return r.headers.get('location')

        # 204 the platform needs more information (namely addresses) to decide what node to use
        data = json.dumps(addresses)
        r = await self.session.post(url, data=data, headers=self.json_headers, allow_redirects=False)
        r.close()
        assert r.status == 303
        return r.headers.get('location')

    async def close(self):
        if self._session:
            await self._session.close()
        await super().close()
