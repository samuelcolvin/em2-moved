from em2.core import Components
from em2.core.utils import BaseServiceCls
from .redis import RedisDNSMixin


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
    prefix = 'pc:'

    async def add_participant(self, conv, participant_addr):
        # TODO this should be async
        d = self.get_domain(participant_addr)
        async with self._redis_pool.get() as redis:
            if not await redis.hexists(self.prefix + conv, d):
                node = await self.get_node(conv, d, participant_addr)
                await redis.hset(conv, d, node)

    async def save_nodes(self, conv, *addresses):
        # TODO this should be async
        async with self._redis_pool.get() as redis:
            domain_lookup = await self.get_nodes(conv, *addresses)
            await redis.hmset(self.prefix + conv, *list(domain_lookup))
        return domain_lookup

    async def remove_domain(self, conv, domain):
        async with self._redis_pool.get() as redis:
            await redis.hdel(self.prefix + conv, domain)

    async def publish(self, action, event_id, data, timestamp):
        # TODO this should be async
        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        domain_lookup = await self.save_nodes(action.conv, *addresses)
        node_urls = domain_lookup.values()
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self.push_data(remote_urls, action, event_id, data, timestamp)

    async def push(self, action, event_id, data, timestamp):
        # TODO this should be async
        async with self._redis_pool.get() as redis:
            node_urls = await redis.hgetall(self.prefix + action.conv)
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        await self.push_data(remote_urls, action, event_id, data, timestamp)

    async def push_data(self, urls, *args):
        raise NotImplementedError
