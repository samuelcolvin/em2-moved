

class BasePropagator:
    async def add_participant(self, con, participant_addr):
        raise NotImplementedError()

    async def remove_participant(self, con, participant_addr):
        raise NotImplementedError()

    async def propagate(self, action, event_id, data, timestamp):
        raise NotImplementedError()

    async def publish(self, con_id, subject, body, participants, timestamp):
        raise NotImplementedError()

    def get_domain(self, address):
        return address[address.index('@'):]


class NullPropagator(BasePropagator):
    """
    Propagator with no functionality to connect to other platforms. Used for testing or trial purposes only.
    """
    async def add_participant(self, action, participant_addr):
        pass

    async def remove_participant(self, action, participant_addr):
        pass

    async def propagate(self, action, event_id, data, timestamp):
        pass

    async def publish(self, con_id, subject, body, participants, timestamp):
        pass
