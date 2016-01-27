from aiopg.sa import create_engine

from em2.ds.pg.models import sa_conversations


async def test_conversation_insert_raw(timestamp, loop, db, dsn):
    async with create_engine(dsn, loop=loop) as engine:
        async with engine.acquire() as conn:
            async with conn.begin() as tr:
                conversation = dict(
                    conv_id='x',
                    creator='user@example.com',
                    subject='testing',
                    ref='testing',
                    timestamp=timestamp,
                    status='draft',
                )
                await conn.execute(sa_conversations.insert().values(**conversation))
                con_count = await conn.scalar(sa_conversations.count())
                assert con_count == 1

                data = None
                async for row in conn.execute(sa_conversations.select()):
                    data = row
                assert data.conv_id == 'x'
                assert data.creator == 'user@example.com'
                assert data.subject == 'testing'
                assert data.timestamp.isoformat() == timestamp.isoformat()
                assert data.status == 'draft'
                await tr.rollback()
