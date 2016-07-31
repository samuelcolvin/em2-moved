from em2.utils import BaseServiceCls
from .redis import RedisDNSMixin

from arq import concurrent


class BasePusher(BaseServiceCls):
    LOCAL = 'L'

    async def add_participant(self, conv, participant_addr):
        raise NotImplementedError()

    async def save_nodes(self, conv, *addresses):
        raise NotImplementedError()

    async def remove_domain(self, conv, domain):
        raise NotImplementedError()

    async def push(self, action, event_id, data, timestamp):
        raise NotImplementedError()

    async def publish(self, action, event_id, data, timestamp):
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

    async def publish(self, action, event_id, data, timestamp):
        pass

    async def get_node(self, conv, domain, *addresses):
        pass


class AsyncRedisPusher(RedisDNSMixin, BasePusher):
    prefix = b'pc:'

    @concurrent
    async def add_participant(self, conv, participant_addr):
        domain = self.get_domain(participant_addr)
        hash_key = self.prefix + conv.encode()
        b_domain = domain.encode()
        async with await self.get_redis_conn() as redis:
            if not await redis.hexists(hash_key, b_domain):
                node = await self.get_node(conv, domain, participant_addr)
                await redis.hset(hash_key, b_domain, node)

    @concurrent
    async def save_nodes(self, conv, *addresses):
        hash_key = self.prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            domain_lookup = await self.get_nodes(conv, *addresses)
            await redis.hmset_dict(hash_key, domain_lookup)
        return domain_lookup

    @concurrent
    async def remove_domain(self, conv, domain):
        hash_key = self.prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            await redis.hdel(hash_key, domain)

    @concurrent
    async def publish(self, action, event_id, data, timestamp):
        from em2.core import Components
        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        domain_lookup = await self.save_nodes(action.conv, *addresses)
        node_urls = domain_lookup.values()
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self.push_data(remote_urls, action, event_id, data, timestamp)

    @concurrent
    async def push(self, action, event_id, data, timestamp):
        async with await self.get_redis_conn() as redis:
            node_urls = await redis.hgetall(self.prefix + action.conv)
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self.push_data(remote_urls, action, event_id, data, timestamp)

    async def push_data(self, urls, *args):
        raise NotImplementedError
