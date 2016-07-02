from copy import deepcopy

from em2.core import Action, Verbs, Components
from em2.comms import BasePropagator


class Network:
    def __init__(self):
        self.platforms = {}

    def add_platform(self, domain, controller):
        assert domain not in self.platforms
        self.platforms[domain] = controller


class SimplePropagator(BasePropagator):
    def __init__(self, network:  Network, local_domain='local.com'):
        self.network = network
        self.conv_platforms = {}
        self.addr_lookups = {}
        self.local_domain = local_domain

    async def add_participant(self, conv, participant_addr):
        platform = await self._get_platform(participant_addr)
        if not platform:
            return
        self.conv_platforms[conv].add(platform)
        self.addr_lookups[conv][participant_addr] = platform

    async def participants_added(self, conv, *addresses):
        self.conv_platforms[conv] = set()
        self.addr_lookups[conv] = {}
        for address in addresses:
            platform = await self._get_platform(address)
            if platform:
                self.conv_platforms[conv].add(platform)
                self.addr_lookups[conv][address] = platform

    async def remove_participant(self, conv, participant_addr):
        platform = await self._get_platform(participant_addr)
        if not platform:
            return
        platform = self.addr_lookups[conv].pop(participant_addr)
        if platform not in self.addr_lookups[conv].values():
            self.conv_platforms[conv].remove(platform)

    async def publish(self, action, event_id, data, timestamp):
        new_action = Action(action.address, action.conv, Verbs.ADD, timestamp=timestamp, event_id=event_id)
        prop_data = deepcopy(data)

        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        await self.participants_added(action.conv, *addresses)
        for address in addresses:
            platform = await self._get_platform(address)
            if platform:
                await platform.act(new_action, data=prop_data)

    async def propagate(self, action, event_id, data, timestamp):
        ctrls = self.conv_platforms[action.conv]

        new_action = Action(action.address, action.conv, action.verb, action.component,
                            item=action.item, timestamp=timestamp, event_id=event_id)
        prop_data = deepcopy(data)
        for ctrl in ctrls:
            await ctrl.act(new_action, **prop_data)

    async def _get_platform(self, address):
        domain = self.get_domain(address)
        if domain == self.local_domain:
            return
        return self.network.platforms[domain]

    def __repr__(self):
        return 'SimplePropagator<{}>'.format(self.local_domain)
