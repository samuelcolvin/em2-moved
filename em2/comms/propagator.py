from em2.core.utils import BaseServiceCls


class BasePropagator(BaseServiceCls):
    async def add_participant(self, conv, participant_addr):
        raise NotImplementedError()

    async def participants_added(self, conv, *addresses):
        raise NotImplementedError()

    async def remove_participant(self, conv, participant_addr):
        raise NotImplementedError()

    async def propagate(self, action, event_id, data, timestamp):
        raise NotImplementedError()

    async def publish(self, action, event_id, data, timestamp):
        raise NotImplementedError()

    def get_domain(self, address):
        return address[address.index('@') + 1:]

    async def _get_platform(self, address):
        raise NotImplementedError()


class NullPropagator(BasePropagator):  # pragma: no cover
    """
    Propagator with no functionality to connect to other platforms. Used for testing or trial purposes only.
    """
    async def add_participant(self, conv, participant_addr):
        pass

    async def participants_added(self, conv, *addresses):
        pass

    async def remove_participant(self, conv, participant_addr):
        pass

    async def propagate(self, action, event_id, data, timestamp):
        pass

    async def publish(self, action, event_id, data, timestamp):
        pass

    async def _get_platform(self, address):
        pass
