import asyncio
import json
import logging
from time import time

from arq import Drain

from em2 import Settings  # noqa
from em2.utils.encoding import msg_decode
from em2.utils.web import Em2JsonEncoder

logger = logging.getLogger('em2.d.background')


class Background:
    def __init__(self, app, loop):
        self.app = app
        self.loop = loop
        self.settings: Settings = app['settings']
        self.up = asyncio.Event(loop=self.loop)
        self.ready = asyncio.Event(loop=self.loop)
        self.redis_pool = None  # set in _process_actions
        self.task = loop.create_task(self._process_actions())
        self.recipients_key = self.settings.FRONTEND_RECIPIENTS_BASE.format(self.app['name'])
        self._last_added_recipient = 0
        self.connections = {}

    async def add_recipient(self, id, ws=None):
        await self.up.wait()
        if ws:
            self.connections[id] = ws
        async with self.redis_pool.get() as redis:
            await asyncio.gather(
                redis.sadd(self.recipients_key, id),
                redis.expire(self.recipients_key, 60),
            )
        self._last_added_recipient = time()

    async def remove_recipient(self, id):
        self.connections.pop(id)
        async with self.redis_pool.get() as redis:
            await redis.srem(self.recipients_key, id)

    async def close(self):
        logger.info('closing frontend background task, done: %r', self.task.done())
        if self.redis_pool:
            async with self.redis_pool.get() as redis:
                await redis.delete(self.recipients_key)
        if self.task.done():
            self.task.result()
        self.task.cancel()

    async def _process_actions(self):
        self.redis_pool = await self.app['pusher'].get_redis_pool()
        jobs_key = self.settings.FRONTEND_JOBS_BASE.format(self.app['name'])
        self.up.set()
        await self.add_recipient(0)
        self.ready.set()
        drain = Drain(
            redis_pool=self.redis_pool,
            burst_mode=False,
            max_concurrent_tasks=5,
            raise_task_exception=True,
        )
        async with drain:
            logger.info('starting background drain loop...')
            async for _, raw_data in drain.iter(jobs_key, pop_timeout=30):
                if raw_data:
                    drain.add(self._send_action, raw_data)
                if (time() - self._last_added_recipient) >= 20:
                    await self.add_recipient(0)

    async def _send_action(self, raw_data):
        data = msg_decode(raw_data)
        logger.info('processing action with %d recipients, %d current ws connections',
                    len(data['recipients']), len(self.connections))
        send_data = json.dumps(data['action'], cls=Em2JsonEncoder)
        for recipient_id in data['recipients']:
            ws = self.connections.get(recipient_id)
            if ws:
                ws.send_str(send_data)
            else:
                logger.warning('no ws connection for %d', recipient_id)
