import base64
import os
from textwrap import wrap

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2.exceptions import DomainPlatformMismatch, FailedInboundAuthentication, PlatformForbidden
from em2.utils import BaseServiceCls, now_unix_secs

from .redis import RedisDNSMixin, RedisMethods


class BaseAuthenticator(BaseServiceCls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._head_request_timeout = self._settings.COMMS_HEAD_REQUEST_TIMEOUT
        self._domain_timeout = self._settings.COMMS_DOMAIN_CACHE_TIMEOUT
        self._platform_token_timeout = self._settings.COMMS_PLATFORM_TOKEN_TIMEOUT
        self._past_ts_limit, self._future_ts_limit = self._settings.COMMS_AUTHENTICATION_TS_LENIENCY
        self._token_length = self._settings.COMMS_PLATFORM_TOKEN_LENGTH

    async def authenticate_platform(self, platform: str, timestamp: int, signature: str):
        """
        Check a request is "from" a domain by asserting that the signature of the supplied string is valid.
        :param platform: domain of platform being authenticated
        :param timestamp: unix timestamp in seconds, must be close to now
        :param signature: signature of platform_timestamp
        :return: new API token for the platform which is valid for COMMS_PLATFORM_TOKEN_TIMEOUT
        """

        now = self._now_unix()
        l_limit, u_limit = now + self._past_ts_limit, now + self._future_ts_limit
        if not l_limit < timestamp < u_limit:
            raise FailedInboundAuthentication('{} was not between {} and {}'.format(timestamp, l_limit, u_limit))

        public_key = await self._get_public_key(platform)
        signed_message = '{}:{}'.format(platform, timestamp)
        if not self._valid_signature(signed_message, signature, public_key):
            raise FailedInboundAuthentication('invalid signature')
        token_expires_at = now + self._domain_timeout
        platform_token = '{}:{}:{}'.format(platform, token_expires_at, self._generate_random())
        await self._store_platform_token(platform_token, token_expires_at)
        return platform_token

    async def valid_platform_token(self, token):
        if not await self.key_exists(token):
            raise PlatformForbidden('platform "{}" not found'.format(token))
        return token.split(':', 1)[0]

    async def check_domain_platform(self, domain, platform):
        if not await self._check_domain_uses_platform(domain, platform):
            raise DomainPlatformMismatch('"{}" does not use "{}"'.format(domain, platform))

    async def key_exists(self, key: str):
        raise NotImplementedError

    async def _get_public_key(self, platform: str):
        raise NotImplementedError

    async def _store_platform_token(self, token, expires_at):
        raise NotImplementedError

    async def _check_domain_uses_platform(self, domain, platform_domain):
        raise NotImplementedError

    def _valid_signature(self, signed_message, signature, public_key):
        try:
            key = RSA.importKey(public_key)
        except ValueError as e:
            raise FailedInboundAuthentication(*e.args) from e

        # signature needs to be decoded from base64
        signature = base64.urlsafe_b64decode(signature)

        h = SHA256.new(signed_message.encode())
        cipher = PKCS1_v1_5.new(key)
        return cipher.verify(h, signature)

    def _now_unix(self):
        return now_unix_secs()

    def _generate_random(self):
        return base64.urlsafe_b64encode(os.urandom(self._token_length))[:self._token_length].decode()


class RedisDNSAuthenticator(RedisMethods, BaseAuthenticator, RedisDNSMixin):
    async def _get_public_key(self, platform: str):
        dns_results = await self.resolver.query(platform, 'TXT')
        key_data = self._get_public_key_from_dns(dns_results)
        # return the key in a format openssl / RSA.importKey can cope with
        return '-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n'.format('\n'.join(wrap(key_data, width=65)))

    def _get_public_key_from_dns(self, dns_results: str):
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
        raise FailedInboundAuthentication('no "em2key" TXT dns record found')

    async def _check_domain_uses_platform(self, domain: str, platform_domain: str):
        cache_key = b'pl:%s' % domain.encode()
        async with await self.get_redis_conn() as redis:
            cache_p = await redis.get(cache_key)
            if cache_p and cache_p.decode() == platform_domain:
                return True
            results = await self.resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
            for _, host in results:
                if host == platform_domain:
                    await redis.setex(cache_key, self._domain_timeout, host.encode())
                    return True

    async def _store_platform_token(self, token: str, expires_at: int):
        async with await self.get_redis_conn() as redis:
            await self.set_exat(redis, token.encode(), self._dft_value, expires_at)
