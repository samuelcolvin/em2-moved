import os
import base64
from datetime import datetime
from textwrap import wrap

from Crypto.Signature import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256

from em2.exceptions import FailedAuthentication, PlatformForbidden, DomainPlatformMismatch
from em2.utils import to_unix_timestamp, BaseServiceCls
from .redis import RedisDNSMixin


class BaseAuthenticator(BaseServiceCls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._head_request_timeout = self._settings.COMMS_HEAD_REQUEST_TIMEOUT
        self._domain_timeout = self._settings.COMMS_DOMAIN_CACHE_TIMEOUT
        self._platform_key_timeout = self._settings.COMMS_PLATFORM_KEY_TIMEOUT
        self._past_ts_limit, self._future_ts_limit = self._settings.COMMS_AUTHENTICATION_TS_LENIENCY
        self._key_length = self._settings.COMMS_PLATFORM_KEY_LENGTH

    async def authenticate_platform(self, platform: str, timestamp: int, signature: str):
        """
        Check a request is "from" a domain by asserting that the signature of the supplied string is valid.
        :param platform: domain of platform being authenticated
        :param timestamp: unix timestamp, must be close to now
        :param signature: signature of platform_timestamp
        :return: new API key for the platform which is valid for COMMS_PLATFORM_KEY_TIMEOUT
        """

        now = self._now_unix()
        lower_limit, upper_limit = now + self._past_ts_limit, now + self._future_ts_limit
        if not lower_limit < timestamp < upper_limit:
            raise FailedAuthentication('{} was not between {} and {}'.format(timestamp, lower_limit, upper_limit))

        public_key = await self._get_public_key(platform)
        signed_message = '{}:{}'.format(platform, timestamp)
        if not self._valid_signature(signed_message, signature, public_key):
            raise FailedAuthentication('invalid signature')
        key_expiresat = now + self._domain_timeout
        platform_key = '{}:{}:{}'.format(platform, key_expiresat, self._generate_random())
        await self._store_key(platform_key, key_expiresat)
        return platform_key

    async def valid_platform_token(self, platform_token):
        if not await self._platform_token_exists(platform_token):
            raise PlatformForbidden('platform "{}" not found'.format(platform_token))

    async def check_domain_platform(self, domain, platform_token):
        platform_domain = platform_token.split(':', 1)[0]
        if not await self._check_domain_uses_platform(domain, platform_domain):
            raise DomainPlatformMismatch('"{}" does not use "{}"'.format(domain, platform_domain))

    async def _platform_token_exists(self, platform_token):
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

        # signature needs to be decoded from base64
        signature = base64.urlsafe_b64decode(signature)

        h = SHA256.new(signed_message.encode('utf8'))
        cipher = PKCS1_v1_5.new(key)
        return cipher.verify(h, signature)

    def _now_unix(self):
        return to_unix_timestamp(datetime.utcnow())

    def _generate_random(self):
        return base64.urlsafe_b64encode(os.urandom(self._key_length))[:self._key_length].decode('utf8')


class RedisDNSAuthenticator(BaseAuthenticator, RedisDNSMixin):
    async def _platform_token_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return await redis.exists(platform_token.encode())

    async def _store_key(self, key: str, expiresat: int):
        async with await self.get_redis_conn() as redis:
            pipe = redis.pipeline()
            b_key = key.encode()
            pipe.set(b_key, self._dft_value)
            pipe.expireat(b_key, expiresat)
            await pipe.execute()

    async def _get_public_key(self, platform: str):
        dns_results = await self.resolver.query(platform, 'TXT')
        key_data = self._get_key(dns_results)
        # return the key in a format openssl / RSA.importKey can cope with
        return '-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n'.format('\n'.join(wrap(key_data, width=65)))

    def _get_key(self, dns_results: str):
        results = (r.text for r in dns_results)
        for r in results:
            if r.lower().startswith('v=em2key'):
                # [8:] removes the v=em2key, [2:] remove the p=
                key = r[8:].strip()[2:]
                for extra in results:
                    key += extra.strip()
                    if extra.endswith('='):
                        # key finished
                        return key
        raise FailedAuthentication('no "em2key" TXT dns record found')

    async def _check_domain_uses_platform(self, domain: str, platform_domain: str):
        cache_key = b'pl:%s' % domain.encode()
        async with await self.get_redis_conn() as redis:
            platform = await redis.get(cache_key)
            if platform and platform.decode() == platform_domain:
                return True
            results = await self.resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
            for _, platform in results:
                if platform == platform_domain:
                    await redis.setex(cache_key, self._domain_timeout, platform.encode())
                    return True
