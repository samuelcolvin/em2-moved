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
        self.remotes = {}
        self.network = Network()

    async def add_participant(self, conv, participant_addr):
        d = self.get_domain(participant_addr)
        if d not in self.remotes[conv]:
            self.remotes[conv][d] = await self.get_node(conv, d, participant_addr)

    async def save_nodes(self, conv, *addresses):
        self.remotes[conv] = await self.get_nodes(conv, *addresses)

    async def remove_domain(self, conv, domain):
        self.remotes[conv].pop(domain)

    async def publish(self, action, event_id, data):
        new_action = Action(action.address, action.conv, Verbs.ADD, timestamp=action.timestamp, event_id=event_id)
        prop_data = deepcopy(data)

        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        await self.save_nodes(action.conv, *addresses)
        for ctrl in set(self.remotes[action.conv].values()):
            if ctrl != self.LOCAL:
                await ctrl.act(new_action, data=prop_data)

    async def push(self, action, event_id, data):
        new_action = Action(action.address, action.conv, action.verb, action.component,
                            item=action.item, timestamp=action.timestamp, event_id=event_id)
        prop_data = deepcopy(data)
        for ctrl in set(self.remotes[action.conv].values()):
            if ctrl != self.LOCAL:
                await ctrl.act(new_action, **prop_data)

    async def get_node(self, conv, domain, *addresses):
        return self.LOCAL if domain == self._settings.LOCAL_DOMAIN else self.network.nodes[domain]


class HttpMockedDNSPusher(HttpDNSPusher):
    @property
    def resolver(self):
        return MockDNSResolver()
