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

    @property
    def all_platform_count(self):
        return len(self.all_platforms)

    @property
    def active_platform_count(self):
        return len(self.active_platforms)

    async def add_participant(self, con, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.all_platforms[domain]
        if con in self.active_platforms:
            self.active_platforms[con].add(platform)
            self.addr_lookups[con][participant_addr] = platform
        else:
            self.active_platforms[con] = {platform}
            self.addr_lookups[con] = {participant_addr: platform}

    async def remove_participant(self, con, participant_addr):
        domain = self.get_domain(participant_addr)
        if domain == self.local_domain:
            return
        platform = self.addr_lookups[con].pop(participant_addr)
        if platform not in self.addr_lookups[con].values():
            self.active_platforms[con].remove(platform)

    async def propagate(self, action, data, timestamp):
        try:
            ctrls = self.active_platforms[action.con]
        except KeyError:
            con_obj = action.ds.ds.get_con(action.con)
            # con_id has changed, update active_platforms to correct key
            ctrls = self.active_platforms.pop(con_obj['draft_con_id'])
            self.active_platforms[action.con] = ctrls

        new_action = Action(action.actor_addr, action.con, action.verb, action.component, action.item, timestamp, True)
        for ctrl in ctrls:
            await ctrl.act(new_action, **data)

    def __repr__(self):
        return 'SimplePropagator<{}>'.format(self.local_domain)
