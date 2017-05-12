import asyncpg
from asyncpg.pool import Pool  # noqa

from em2 import Settings


class Database:
    def __init__(self, loop, settings: Settings):
        self._loop = loop
        self._settings = settings
        self._pool: Pool = None

    async def startup(self):
        self._pool = await asyncpg.create_pool(
            dsn=self._settings.pg_dsn,
            min_size=self._settings.PG_POOL_MINSIZE,
            max_size=self._settings.PG_POOL_MAXSIZE,
            loop=self._loop,
        )
        await self._pool.execute("SET TIME ZONE 'UTC';")

    def acquire(self, *, timeout=None):
        return self._pool.acquire(timeout=timeout)

    async def close(self):
        return await self._pool.close()
