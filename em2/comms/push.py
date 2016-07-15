from em2.core.utils import BaseServiceCls


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

    async def get_node(self, domain):
        raise NotImplementedError()

    async def get_nodes(self, *addresses):
        domains = {}
        for address in addresses:
            d = self.get_domain(address)
            if d not in domains:
                domains[d] = await self.get_node(d)
        return domains


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

    async def get_node(self, domain):
        pass
