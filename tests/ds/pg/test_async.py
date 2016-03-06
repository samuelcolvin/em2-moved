import pytest
from aiopg.sa import create_engine

from em2.core import Controller, Action, Verbs
from em2.core.exceptions import ConversationNotFound
from em2.ds.pg.datastore import PostgresDataStore
from em2.ds.pg.models import sa_conversations

from tests.fixture_classes import NullPropagator


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


async def test_datastore_setup(loop, empty_db, dsn):
    async with create_engine(dsn, loop=loop, timeout=5) as engine:
        ds = PostgresDataStore(engine)
        controller = Controller(ds, NullPropagator())
        async with ds.connection() as conn:
            await ds.create_user(conn, 'sender@example.com')

        async with ds.connection() as conn:
            action = Action('sender@example.com', None, Verbs.ADD)
            conv_id = await controller.act(action, subject='the subject')
            cds = ds.new_conv_ds(conv_id, conn)
            props = await cds.get_core_properties()
            assert props.subject == 'the subject'


async def test_datastore_rollback(loop, empty_db, dsn, timestamp):
    async with create_engine(dsn, loop=loop, timeout=5) as engine:
        ds = PostgresDataStore(engine)
        controller = Controller(ds, NullPropagator())
        line = 0
        with pytest.raises(ConversationNotFound):
            async with controller.ds.connection() as conn:
                conversation = dict(conv_id='x', creator='x', subject='x', ref='x', timestamp=timestamp, status='draft')
                await conn.execute(sa_conversations.insert().values(**conversation))
                con_count = await conn.scalar(sa_conversations.count())
                assert con_count == 1
                cds = ds.new_conv_ds('123', conn)
                line = 1
                await cds.get_core_properties()
                line = 2

        assert line == 1  # check the above snippet gets to the right place
        # connection above should rollback on ConversationNotFound so there should now be no conversations
        async with controller.ds.connection() as conn:
            con_count = await conn.scalar(sa_conversations.count())
            assert con_count == 0
