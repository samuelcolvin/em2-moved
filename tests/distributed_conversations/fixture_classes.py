from em2.base import Action
from em2.send import BasePropagator


class SimplePropagator(BasePropagator):
    def __init__(self, local_domain='@local.com'):
        self.all_platforms = {}
        self.active_platforms = {}
        self.addr_lookups = {}
        self.local_domain = local_domain

    def add_platform(self, domain, controller):
        assert domain not in self.all_platforms
        self.all_platforms[domain] = controller

    async def add_participant(self, action, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.all_platforms[domain]
        if action.con in self.active_platforms:
            self.active_platforms[action.con].add(platform)
            self.addr_lookups[action.con][participant_addr] = platform
        else:
            self.active_platforms[action.con] = {platform}
            self.addr_lookups[action.con] = {participant_addr: platform}

    async def remove_participant(self, action, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.addr_lookups[action.con].pop(participant_addr)
        if platform not in self.addr_lookups[action.con].values():
            self.active_platforms[action.con].remove(platform)

    async def propagate(self, action, item, data, timestamp):
        ctrls = self.active_platforms[action.con]
        new_action = Action(action.actor_addr, action.con, action.verb, action.component, item, True)
        for ctrl in ctrls:
            await ctrl.act(new_action)

    # async def publish(self, con_id, creator, subject, body, participants, timestamp):
    #     ctrls = self.active_platforms[con_id]
    #     new_action = Action(creator, con_id,  action.con, action.verb, action.component, item, True)
    #     for ctrl in ctrls:
    #         await ctrl.act(new_action)
