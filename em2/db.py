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

    def acquire(self, *, timeout=None):
        return self._pool.acquire(timeout=timeout)

    async def close(self):
        return await self._pool.close()


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update is slightly ugly, but should happen vary rarely.
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def set_recipient(request):
    if request['session'].recipient_id:
        return
    recipient_id = await request['conn'].fetchval(GET_RECIPIENT_ID, request['session'].address)
    if recipient_id is None:
        recipient_id = await request['conn'].fetchval(SET_RECIPIENT_ID, request['session'].address)
    request['session'].recipient_id = recipient_id
    # until samuelcolvin/pydantic#14 is fixed
    request['session'].__values__['recipient_id'] = recipient_id
    request['session_change'] = True


LIST_CONVS = """
SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
FROM (
  SELECT c.hash as conv_id, c.draft_hash as draft_conv_id, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  LEFT OUTER JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1
  ORDER BY c.id DESC LIMIT 50
) t;
"""


async def conversations_json(request):
    return await request['conn'].fetchval(LIST_CONVS, request['session'].recipient_id)


CONV_DETAILS = """
SELECT row_to_json(t)
FROM (
  SELECT c.hash as conv_id, c.draft_hash as draft_conv_id, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  LEFT OUTER JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1 AND c.hash = $2
) t;
"""


async def conversation_details(request, conv_id):
    return await request['conn'].fetchval(CONV_DETAILS, request['session'].recipient_id, conv_id)
