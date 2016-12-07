from copy import deepcopy

from em2.comms import BasePusher
from em2.comms.http.push import HttpDNSPusher
from em2.core import Action, Components, Verbs

from .authenicator import MockDNSResolver


class Network:
    def __init__(self):
        self.nodes = {}

    def add_node(self, domain, controller):
        assert domain not in self.nodes
        self.nodes[domain] = controller


class SimplePusher(BasePusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.network = Network()

    async def publish(self, action, event_id, data):
        new_action = Action(action.address, action.conv, Verbs.ADD, timestamp=action.timestamp, event_id=event_id)
        prop_data = deepcopy(data)

        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        nodes = await self.get_nodes(*addresses)

        for ctrl in nodes:
            if ctrl != self.LOCAL:
                await ctrl.act(new_action, data=prop_data)

    async def push(self, action, event_id, data, addresses):
        new_action = Action(action.address, action.conv, action.verb, action.component,
                            item=action.item, timestamp=action.timestamp, event_id=event_id)
        prop_data = deepcopy(data)
        nodes = await self.get_nodes(*addresses)
        for ctrl in nodes:
            if ctrl != self.LOCAL:
                await ctrl.act(new_action, **prop_data)

    async def get_node(self, domain):
        return self.LOCAL if domain == self.settings.LOCAL_DOMAIN else self.network.nodes[domain]

    def __str__(self):
        return repr(self)


class HttpMockedDNSPusher(HttpDNSPusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mx_query_count = 0

    @property
    def resolver(self):
        return MockDNSResolver()

    def mx_query(self, host):
        self._mx_query_count += 1
        return super().mx_query(host)
