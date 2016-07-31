import json
from em2.comms.push import AsyncRedisPusher
import aiohttp


class HttpDNSPusher(AsyncRedisPusher):
    json_headers = {'content-type': 'application/json'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = aiohttp.ClientSession(loop=self.loop)

    async def get_node(self, conv, domain, *addresses):
        cache_key = 'nd:{}:{}'.format(conv, domain)
        async with self._redis_pool.get() as redis:
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
                    await redis.setex(cache_key, self._settings.COMMS_DOMAIN_CACHE_TIMEOUT, platform)
                    return node
            # TODO SMTP fallback

    async def try_node(self, conv, platform_domain, addresses):
        url = 'em2.{}/lookup/{}'.format(platform_domain, conv)
        with aiohttp.Timeout(self._settings.COMMS_HTTP_TIMEOUT):
            # TODO authentication, error checking
            r = await self._session.head(url, allow_redirects=False)
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
            r = await self._session.post(url, data=data, headers=self.json_headers, allow_redirects=False)
            r.close()
            assert r.status == 303
            return r.headers.get('location')
