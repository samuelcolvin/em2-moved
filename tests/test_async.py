import datetime

import pytz
from aiopg.sa import create_engine

from em2pg.models import conversations


async def test_conversation_insert_raw(db, dsn):
    async with create_engine(str(dsn)) as engine:
        async with engine.acquire() as conn:
            async with conn.begin() as tr:
                n = pytz.utc.localize(datetime.datetime.now())
                conversation = dict(
                    global_id='x',
                    creator='user@example.com',
                    subject='testing',
                    timestamp=n,
                    status='draft',
                )
                await conn.execute(conversations.insert().values(**conversation))
                con_count = await conn.scalar(conversations.count())
                assert con_count == 1

                data = None
                async for row in conn.execute(conversations.select()):
                    data = row
                assert data.global_id == 'x'
                assert data.creator == 'user@example.com'
                assert data.subject == 'testing'
                assert data.timestamp.isoformat() == n.isoformat()
                assert data.status == 'draft'
                await tr.rollback()
