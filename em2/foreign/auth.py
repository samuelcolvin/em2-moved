import asyncio
import base64
import logging
import os
from datetime import datetime
from textwrap import wrap

import aiodns
from aiodns.error import DNSError
from aiohttp.web_exceptions import HTTPForbidden
from arq import RedisMixin
from arq.jobs import DatetimeJob
from arq.utils import to_unix_ms
from async_timeout import timeout
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2 import Settings
from em2.exceptions import FailedInboundAuthentication

logger = logging.getLogger('em2.foreign.auth')


class Authenticator(RedisMixin):
    job_class = DatetimeJob
    _dft_value = b'1'

    def __init__(self, settings: Settings, *, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        self.redis_settings = self.settings.redis
        super().__init__(**kwargs)
        self._resolver = None
        self._head_request_timeout = self.settings.COMMS_HEAD_REQUEST_TIMEOUT
        self._domain_timeout = self.settings.COMMS_DOMAIN_CACHE_TIMEOUT
        self._platform_token_timeout = self.settings.COMMS_PLATFORM_TOKEN_TIMEOUT
        self._past_ts_limit, self._future_ts_limit = self.settings.COMMS_AUTHENTICATION_TS_LENIENCY
        self._token_length = self.settings.COMMS_PLATFORM_TOKEN_LENGTH

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

    async def validate_platform_token(self, token):
        if not await self.key_exists(token):
            raise HTTPForbidden(text='invalid token')
        return token.split(':', 1)[0]

    async def check_domain_platform(self, domain, platform):
        if not await self._check_domain_uses_platform(domain, platform):
            raise HTTPForbidden(text=f'"{domain}" does not use "{platform}"')

    async def _get_public_key(self, platform: str):
        dns_results = await self.dns_query(platform, 'TXT')
        logger.info('got %d TXT records for %s', len(dns_results), platform)
        key_data = self._get_public_key_from_dns(dns_results)
        # return the key in a format openssl / RSA.importKey can cope with
        return '-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n'.format('\n'.join(wrap(key_data, width=65)))

    def _get_public_key_from_dns(self, dns_results: tuple):
        results = (r.text for r in dns_results)
        for r in results:
            if r.lower().startswith('v=em2key'):
                # [8:] removes the v=em2key, [2:] remove the p=
                key = r[8:].strip()[2:]
                if key.endswith('='):
                    return key
                else:
                    # https://tools.ietf.org/html/rfc4408#section-3.1.3
                    # this could be the wrong interpretation, the above case could suffice
                    for extra in results:
                        key += extra.strip()
                        if extra.endswith('='):
                            # key finished
                            return key
        raise FailedInboundAuthentication('no "em2key" TXT dns record found')

    async def _store_platform_token(self, token: str, expires_at: int):
        async with await self.get_redis_conn() as redis:
            await self.set_exat(redis, token.encode(), self._dft_value, expires_at)

    async def _check_domain_uses_platform(self, domain: str, platform_domain: str):
        cache_key = b'pl:%s' % domain.encode()
        async with await self.get_redis_conn() as redis:
            cache_p = await redis.get(cache_key)
            if cache_p and cache_p.decode() == platform_domain:
                return True
            results = await self.mx_query(domain)
            for _, host in results:
                if host == platform_domain:
                    await redis.setex(cache_key, self._domain_timeout, host.encode())
                    return True

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
        return to_unix_ms(datetime.utcnow())

    def _generate_random(self):
        return base64.urlsafe_b64encode(os.urandom(self._token_length))[:self._token_length].decode()

    @property
    def resolver(self):
        if self._resolver is None:
            nameservers = [self.settings.COMMS_DNS_IP] if self.settings.COMMS_DNS_IP else None
            self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=nameservers)
        return self._resolver

    async def mx_query(self, host):
        results = await self.dns_query(host, 'MX')
        results = [(r.priority, r.host) for r in results]
        results.sort()
        return results

    async def dns_query(self, host, qtype):
        try:
            with timeout(5, loop=self.loop):
                return await self.resolver.query(host, qtype)
        except (DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.warning('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []

    async def set_exat(self, redis, key: bytes, value: str, expires_at: int):
        pipe = redis.pipeline()
        pipe.set(key, value)
        pipe.expireat(key, expires_at)
        await pipe.execute()

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return bool(await redis.exists(platform_token.encode()))
