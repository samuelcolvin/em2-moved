import base64
from datetime import datetime

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from arq import concurrent, Job
from em2.utils import BaseServiceCls, now_unix_secs, to_unix_ms

from .redis import RedisDNSMixin, RedisMethods


class BasePusher(BaseServiceCls):
    LOCAL = 'L'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._early_token_expiry = self._settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY

    async def add_participant(self, conv, participant_addr):
        raise NotImplementedError()

    async def save_nodes(self, conv, *addresses):
        raise NotImplementedError()

    async def remove_domain(self, conv, domain):
        raise NotImplementedError()

    async def push(self, action, event_id, data, timestamp):
        raise NotImplementedError()

    async def publish(self, action, event_id, data):
        raise NotImplementedError()

    def get_domain(self, address):
        return address[address.index('@') + 1:]

    async def get_node(self, conv, domain, *addresses):
        raise NotImplementedError()

    async def get_nodes(self, conv, *addresses):
        domains = {}
        for address in addresses:
            d = self.get_domain(address)
            if d not in domains:
                domains[d] = await self.get_node(conv, d, *addresses)
        return domains

    def get_auth_data(self):
        timestamp = self._now_unix()
        msg = '{}:{}'.format(self._settings.LOCAL_DOMAIN, timestamp)
        h = SHA256.new(msg.encode())

        key = RSA.importKey(self._settings.PRIVATE_DOMAIN_KEY)
        signer = PKCS1_v1_5.new(key)
        signature = base64.urlsafe_b64encode(signer.sign(h)).decode()
        return {
            'platform': self._settings.LOCAL_DOMAIN,
            'timestamp': timestamp,
            'signature': signature,
        }

    async def authenticate(self, domain):
        raise NotImplementedError()

    def _now_unix(self):
        return now_unix_secs()

    def __repr__(self):
        return '{}<{}>'.format(self.__class__.__name__, self._settings.LOCAL_DOMAIN)


class NullPusher(BasePusher):  # pragma: no cover
    """
    Pusher with no functionality to connect to other platforms. Used for testing or trial purposes only.
    """
    async def add_participant(self, conv, participant_addr):
        pass

    async def save_nodes(self, conv, *addresses):
        pass

    async def remove_domain(self, conv, domain):
        pass

    async def push(self, action, event_id, data, timestamp):
        pass

    async def publish(self, action, event_id, data):
        pass

    async def get_node(self, conv, domain, *addresses):
        pass


class UnixtimeJob(Job):
    """
    Converts all datetimes to simple unix timestamps suitable for further encoding.
    """
    @staticmethod
    def msgpack_encoder(obj):
        if isinstance(obj, datetime):
            return int(to_unix_ms(obj))
        return obj


class AsyncRedisPusher(RedisMethods, BasePusher, RedisDNSMixin):
    job_class = UnixtimeJob
    plat_conv_prefix = b'pc:'
    auth_token_prefix = b'ak:'

    @concurrent
    async def add_participant(self, conv, participant_addr):
        domain = self.get_domain(participant_addr)
        hash_key = self.plat_conv_prefix + conv.encode()
        b_domain = domain.encode()
        async with await self.get_redis_conn() as redis:
            if not await redis.hexists(hash_key, b_domain):
                node = await self.get_node(conv, domain, participant_addr)
                await redis.hset(hash_key, b_domain, node)

    @concurrent
    async def save_nodes(self, conv, *addresses):
        hash_key = self.plat_conv_prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            domain_lookup = await self.get_nodes(conv, *addresses)
            await redis.hmset_dict(hash_key, domain_lookup)
        return domain_lookup

    @concurrent
    async def remove_domain(self, conv, domain):
        hash_key = self.plat_conv_prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            await redis.hdel(hash_key, domain)

    async def publish(self, action, event_id, data):
        await self._publish_concurrent(action.attrs, event_id, data)

    @concurrent
    async def _publish_concurrent(self, action_attrs, event_id, data):
        from em2.core import Components
        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        domain_lookup = await self.save_nodes_direct(action_attrs['conv'], *addresses)
        node_urls = domain_lookup.values()
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self._push_data(remote_urls, action_attrs, event_id, data=data)

    @concurrent
    async def push(self, action, event_id, data):
        raise NotImplementedError()
        async with await self.get_redis_conn() as redis:
            node_urls = await redis.hgetall(self.plat_conv_prefix + action.conv)
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self._push_data(remote_urls, action, event_id, data)

    async def _push_data(self, urls, action_attrs, event_id, **kwargs):
        raise NotImplementedError

    async def authenticate(self, domain: str) -> str:
        token_key = self.auth_token_prefix + domain.encode()
        async with await self.get_redis_conn() as redis:
            token = await redis.get(token_key)
            if token:
                return token.decode()
            data = self.get_auth_data()
            token = await self._authenticate_direct(domain, data)
            _, expires_at, _ = token.split(':', 2)
            expire_token_at = int(expires_at) - self._early_token_expiry
            await self.set_exat(redis, token_key, token, expire_token_at)
        return token

    async def _authenticate_direct(self, domain, data):
        raise NotImplementedError()
