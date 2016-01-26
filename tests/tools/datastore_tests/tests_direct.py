import datetime
from em2.core.base import Conversations, perms
from em2.core.common import Components


async def test_create_conversation(data_store):
    async with data_store.connection() as conn:
        ts = datetime.datetime.now()
        await data_store.create_conversation(
            conn,
            conv_id='123',
            creator='test@example.com',
            timestamp=ts,
            ref='x',
            subject='sub',
            status=Conversations.Status.ACTIVE,
        )
        cds = data_store.new_conv_ds('123', conn)
        props = await cds.get_core_properties()
        props = dict(props)
        ts = props.pop('timestamp')
        assert isinstance(ts, datetime.datetime)
        assert props == {
            'subject': 'sub',
            'creator': 'test@example.com',
            'status': 'active',
            'ref': 'x',
            'expiration': None,
        }


async def create_conv(conn, data_store, conv_id='123'):
    ts = datetime.datetime.now()
    await data_store.create_conversation(
        conn,
        conv_id=conv_id,
        creator='test@example.com',
        timestamp=ts,
        ref='x',
        subject='sub',
        status=Conversations.Status.ACTIVE,
    )


async def test_create_first_participant(data_store):
    async with data_store.connection() as conn:
        await create_conv(conn, data_store)
        cds = data_store.new_conv_ds('123', conn)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        assert isinstance(pid, int)
