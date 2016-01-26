from copy import deepcopy

from em2.core.base import Action
from em2.core.propagator import BasePropagator


class SimplePropagator(BasePropagator):
    def __init__(self, local_domain='@local.com'):
        self.all_platforms = {}
        self.active_platforms = {}
        self.addr_lookups = {}
        self.local_domain = local_domain

    def add_platform(self, domain, controller):
        assert domain not in self.all_platforms
        self.all_platforms[domain] = controller

    @property
    def all_platform_count(self):
        return len(self.all_platforms)

    @property
    def active_platform_count(self):
        return len(self.active_platforms)

    async def add_participant(self, conv, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.all_platforms[domain]
        if conv in self.active_platforms:
            self.active_platforms[conv].add(platform)
            self.addr_lookups[conv][participant_addr] = platform
        else:
            self.active_platforms[conv] = {platform}
            self.addr_lookups[conv] = {participant_addr: platform}

    async def remove_participant(self, conv, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.addr_lookups[conv].pop(participant_addr)
        if platform not in self.addr_lookups[conv].values():
            self.active_platforms[conv].remove(platform)

    async def propagate(self, action, data, timestamp):
        try:
            ctrls = self.active_platforms[action.conv]
        except KeyError:
            conv_obj = action.ds.ds.get_conv(action.conv)
            # conv_id has changed, update active_platforms to correct key
            ctrls = self.active_platforms.pop(conv_obj['draft_conv_id'])
            self.active_platforms[action.conv] = ctrls

        new_action = Action(action.actor_addr, action.conv, action.verb, action.component, action.item, timestamp, True)
        prop_data = deepcopy(data)
        for ctrl in ctrls:
            await ctrl.act(new_action, **prop_data)

    def __repr__(self):
        return 'SimplePropagator<{}>'.format(self.local_domain)
