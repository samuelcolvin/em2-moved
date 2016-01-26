from em2.core.propagator import BasePropagator


class NullPropagator(BasePropagator):
    async def add_participant(self, action, participant_addr):
        pass

    async def remove_participant(self, action, participant_addr):
        pass

    async def propagate(self, action, data, timestamp):
        pass
