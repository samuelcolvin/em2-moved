import json
from time import time

from arq import Drain

from em2 import Settings  # noqa
from em2.utils.encoding import msg_decode


class Background:
    def __init__(self, app):
        self.app = app
        self.settings: Settings = app['settings']
        self.task = app.loop.create_task(self._process_actions())
        self.recipients_key = self.settings.FRONTEND_RECIPIENTS_BASE.format(self.app['name'])
        self.redis_pool = None
        self._last_added_recipient = 0

    async def add_recipient(self, id, ws=None):
        if ws:
            self.app['ws'][id] = ws
        async with self.redis_pool.get() as redis:
            pipe = redis.pipeline()
            pipe.sadd(self.recipients_key, id)
            pipe.expire(self.recipients_key, 60)
            await pipe.execute()
        self._last_added_recipient = time()

    async def remove_recipient(self, id):
        self.app['ws'].pop(id)
        async with self.redis_pool.get() as redis:
            await redis.srem(self.recipients_key, id)

    async def close(self):
        async with self.redis_pool.get() as redis:
            await redis.delete(self.recipients_key)
        if self.task.done():
            self.task.result()
        self.task.cancel()

    async def _process_actions(self):
        self.redis_pool = await self.app['pusher'].get_redis_pool()
        jobs_key = self.settings.FRONTEND_JOBS_BASE.format(self.app['name'])
        await self.add_recipient(0)
        drain = Drain(
            redis_pool=self.redis_pool,
            burst_mode=False,
            max_concurrent_tasks=2,
            raise_task_exception=True,
        )
        async with drain:
            async for _, raw_data in drain.iter(jobs_key, pop_timeout=30):
                if raw_data:
                    data = msg_decode(raw_data)
                    send_data = json.dumps(data['action'])
                    for recipient_id in data['recipients']:
                        ws = self.app['ws'].get(recipient_id)
                        if ws:
                            ws.send_str(send_data)
                if (time() - self._last_added_recipient) >= 20:
                    await self.add_recipient(0)
