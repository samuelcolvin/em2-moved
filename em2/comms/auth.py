import os
import asyncio
import base64
from datetime import datetime
from textwrap import wrap

import aiodns
import aioredis
from Crypto.Signature import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256

from em2.exceptions import FailedAuthentication, PlatformForbidden, DomainPlatformMismatch
from em2 import Settings


class BaseAuthenticator:
    def __init__(self, settings: Settings=None, loop: asyncio.AbstractEventLoop=None):
        self._loop = loop
        settings = settings or Settings()
        self._head_request_timeout = settings.COMMS_HEAD_REQUEST_TIMEOUT
        self._domain_timeout = settings.COMMS_DOMAIN_CACHE_TIMEOUT
        self._platform_key_timeout = settings.COMMS_PLATFORM_KEY_TIMEOUT
        self._past_ts_limit, self._future_ts_limit = settings.COMMS_AUTHENTICATION_TS_LENIENCY
        self._key_length = settings.COMMS_PLATFORM_KEY_LENGTH
        self._epoch = datetime(1970, 1, 1)

    async def authenticate_platform(self, platform_timestamp: str, signature: str):
        """
        Check a request is "from" a domain by asserting that the signature of the supplied string is valid.
        :param platform_timestamp: string "<platform>:<timestamp>", timestamp must be close to now
        :param signature: signature of platform_timestamp
        :return: new API key for the platform which is valid for COMMS_PLATFORM_KEY_TIMEOUT
        """
        platform, timestamp = platform_timestamp.split(':', 1)
        try:
            ts_int = int(timestamp)
        except ValueError:
            raise FailedAuthentication('"{}" is not a valid timestamp'.format(timestamp))

        now = self._now_unix()
        lower_limit, upper_limit = now + self._past_ts_limit, now + self._future_ts_limit
        if not lower_limit < ts_int < upper_limit:
            raise FailedAuthentication('{} was not between {} and {}'.format(ts_int, lower_limit, upper_limit))

        public_key = await self._get_public_key(platform)
        if not self._valid_signature(platform_timestamp, signature, public_key):
            raise FailedAuthentication('invalid signature')
        key_expiresat = now + self._domain_timeout
        platform_key = '{}:{}:{}'.format(platform, key_expiresat, self._generate_random())
        await self._store_key(platform_key, key_expiresat)
        return platform_key

    async def valid_platform_key(self, platform_key):
        if not await self._platform_key_exists(platform_key):
            raise PlatformForbidden('platform "{}" not found'.format(platform_key))

    async def check_domain(self, domain, platform_key):
        await self.valid_platform_key(platform_key)

        platform_domain = platform_key.split(':', 1)[0]
        if not await self._check_domain_uses_platform(domain, platform_domain):
            raise DomainPlatformMismatch('"{}" does not use "{}"'.format(domain, platform_domain))

    async def _platform_key_exists(self, platform_key):
        raise NotImplementedError

    async def _get_public_key(self, platform):
        raise NotImplementedError

    async def _store_key(self, key, expiresat):
        raise NotImplementedError

    async def _check_domain_uses_platform(self, domain, platform_domain):
        raise NotImplementedError

    def _valid_signature(self, signed_message, signature, public_key):
        try:
            key = RSA.importKey(public_key)
        except ValueError as e:
            raise FailedAuthentication(*e.args) from e

        # signature needs to decoded from base64
        signature = base64.urlsafe_b64decode(signature)

        h = SHA256.new(signed_message.encode('utf8'))
        cipher = PKCS1_v1_5.new(key)
        return cipher.verify(h, signature)

    def _now_unix(self):
        return int((datetime.utcnow() - self._epoch).total_seconds())

    def _generate_random(self):
        return base64.urlsafe_b64encode(os.urandom(self._key_length))[:self._key_length].decode('utf8')


class RedisAuthenticator(BaseAuthenticator):
    __resolver = None
    _v = '1'

    def __init__(self, settings: Settings=None, loop: asyncio.AbstractEventLoop=None):
        super().__init__(settings, loop)
        self._redis_pool = loop.run_until_complete(self.__redis_pool(settings.REDIS_CONN))

    async def __redis_pool(self, conn):
        return await aioredis.create_pool((conn['host'], conn['port']), encoding='utf8', loop=self._loop)

    @property
    def _resolver(self):
        if self.__resolver is None:
            self.__resolver = aiodns.DNSResolver(loop=self._loop)
        return self.__resolver

    async def _platform_key_exists(self, platform_key):
        async with self._redis_pool.get() as redis:
            return await redis.exists(platform_key)

    async def _store_key(self, key, expiresat):
        async with self._redis_pool.get() as redis:
            pipe = redis.pipeline()
            pipe.set(key, self._v)
            pipe.expireat(key, expiresat)
            await pipe.execute()

    async def _get_public_key(self, platform):
        dns_results = await self._resolver.query(platform, 'TXT')
        key_data = self._get_key(dns_results)
        # return the key in a format openssl / RSA.importKey can cope with
        return '-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n'.format('\n'.join(wrap(key_data, width=65)))

    def _get_key(self, dns_results):
        results = (r.text for r in dns_results)
        for r in results:
            if r.lower().startswith('v=em2key'):
                # [8:] removes the v=em2key, [2:] remove the p=
                key = r[8:].strip()[2:]
                for extra in results:
                    key += extra.strip()
                    if extra.endswith('=='):
                        # key finished
                        return key

    async def _check_domain_uses_platform(self, domain, platform_domain):
        cache_key = 'dm:{}'.format(domain)
        async with self._redis_pool.get() as redis:
            platform = await redis.get(cache_key)
            if platform == platform_domain:
                return True
            results = await self._resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
            for _, platform in results:
                if platform == platform_domain:
                    await redis.setex(cache_key, self._domain_timeout, platform)
                    return True

    # __session = None
    #
    # @property
    # def _session(self):
    #     if self.__session is None:
    #         self.__session = aiohttp.ClientSession(loop=self._loop)
    #     return self.__session
    #
    # url = 'https://{}/-/status/'.format(platform)
    # try:
    #     r_future = self._session.head(url, allow_redirects=False)
    #     r = await
    #     asyncio.wait_for(r_future, self._head_request_timeout)
    #     assert r.status_code == 200, 'unexpected status code: {}'.format(r.status_code)
    #     # TODO in time we should check em2 version compatibility
    #     assert 'em2version' in r.headers, 'em2version missing from headers {}'.format(r.headers)
    # except (ClientError, TimeoutError, AssertionError):
    #     return
    # return platform_key