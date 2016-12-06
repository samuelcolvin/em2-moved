import datetime

from em2.core import Components, perms

from .test_conversations import create_conv


async def test_list_conversations(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds1 = await create_conv(conn, ds, '123')
        await cds1.add_component(Components.PARTICIPANTS, address='test1@ex.com', permissions=perms.FULL)

        cds2 = await create_conv(conn, ds, '456')
        await cds2.add_component(Components.PARTICIPANTS, address='test2@ex.com', permissions=perms.FULL)

        convs = await ds.list_conversations(conn, 'test1@ex.com')
        assert len(convs) == 1
        assert isinstance(convs[0].pop('timestamp'), datetime.datetime)
        assert convs[0] == {
            'creator': 'test@example.com',
            'ref': 'x',
            'status': 'active',
            'expiration': None,
            'subject': 'sub',
            'conv_id': '123',
        }


async def test_list_lots_of_conversations(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        for i in range(10):
            cds1 = await create_conv(conn, ds, str(i))
            await cds1.add_component(Components.PARTICIPANTS, address='test1@ex.com', permissions=perms.FULL)

        convs = await ds.list_conversations(conn, 'test1@ex.com')
        assert [c['conv_id'] for c in convs] == ['9', '8', '7', '6', '5', '4', '3', '2', '1', '0']
