# from em2.comms.worker import Worker
from arq import BaseWorker


class RaiseWorker(BaseWorker):

    @classmethod
    async def handle_exc(cls, started_at, exc, j):
        raise exc
