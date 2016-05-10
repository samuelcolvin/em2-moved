import asyncio
import aiohttp
from aiohttp import ClientError
import aiodns

from em2.core.exceptions import ResolverException


class Resolver:
    def __init__(self, redis_pool, loop, settings):
        self._rpool = redis_pool
        self._resolver = aiodns.DNSResolver(loop=loop)
        self._session = aiohttp.ClientSession(loop=loop)
        self._head_timeout = settings.COMMS_REQUEST_HEAD_TIMEOUT
        self._domain_timeout = settings.COMMS_DOMAIN_CACHE_TIMEOUT
        self._platform_timeout = settings.COMMS_PLATFORM_CACHE_TIMEOUT

    async def get_platform(self, domain: str):
        """
        Find the highest priority em2 platform from a domain's MX records. Results are cached for 24 hours.
        :param domain: domain
        :return:
        """
        cache_key = 'dm:{}'.format(domain)
        async with self._rpool.get() as redis:
            platform = await redis.get(cache_key)
            if platform:
                return platform, await self.get_platform_key(platform, redis)
            results = await self._resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
            for _, platform in results:
                platform_key = await self.get_platform_key(platform, redis)
                if platform_key:
                    await redis.setex(cache_key, self._domain_timeout, platform)
                    return platform, platform_key
        raise ResolverException('no platform found for domain "{}"'.format(domain))

    async def get_platform_key(self, platform_domain, redis):
        cache_key = 'plat:{}'.format(platform_domain)
        platform_key = await redis.get(cache_key)
        if platform_key:
            return platform_key
        results = await self._resolver.query(platform_domain, 'TXT')
        try:
            platform_key = next(r for r in results if r.startswith('em2key:'))[7:].strip()
        except StopIteration:
            return
        url = 'https://{}/-/status/'.format(platform_domain)
        try:
            r_future = self._session.head(url, allow_redirects=False)
            r = await asyncio.wait_for(r_future, self._head_timeout)
            assert r.status_code == 200, 'unexpected status code: {}'.format(r.status_code)
            # TODO in time we should check em2 version compatibility
            assert 'em2version' in r.headers, 'em2version missing from headers {}'.format(r.headers)
        except (ClientError, TimeoutError, AssertionError):
            return
        await redis.setex(cache_key, self._platform_timeout, platform_key)
        return platform_key
