import pytest

from em2.core import Components, perms
from em2.exceptions import ComponentNotFound

from .test_conversations import create_conv


async def test_add_component_message(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(Components.PARTICIPANTS, address='test@example.com', permissions=perms.FULL)
        await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=timestamp,
            body='hello',
            parent=None,
        )
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        message = dict(messages[0])
        assert message['timestamp'].isoformat() == timestamp.isoformat()
        assert message['id'] == 'm123'
        assert message['author'] == pid
        assert message['body'] == 'hello'
        assert message['parent'] is None
        # TODO test other things eg. locked


async def test_edit_component_message(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(Components.PARTICIPANTS, address='test@example.com', permissions=perms.FULL)
        msg_local_id = await cds.add_component(
            Components.MESSAGES,
            id='m1',
            author=pid,
            timestamp=timestamp,
            body='hello',
            parent=None,
        )
        await cds.add_component(Components.MESSAGES, id='m2', author=pid, timestamp=timestamp, body='hello2')
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 2
        message1 = next(m for m in messages if m['id'] == 'm1')
        assert message1['timestamp'].isoformat() == timestamp.isoformat()
        assert message1['body'] == 'hello'
        message2 = next(m for m in messages if m['id'] == 'm2')
        assert message2['body'] == 'hello2'

        await cds.edit_component(
            Components.MESSAGES,
            msg_local_id,
            body='this is a different body',
        )

        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 2
        message1 = next(m for m in messages if m['id'] == 'm1')
        assert message1['timestamp'].isoformat() == timestamp.isoformat()
        assert message1['body'] == 'this is a different body'

        message2 = next(m for m in messages if m['id'] == 'm2')
        assert message2['body'] == 'hello2'


async def test_message_meta(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(Components.PARTICIPANTS, address='test@example.com', permissions=perms.FULL)
        msg_local_id = await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=timestamp,
            body='hello',
        )
        msg_meta = await cds.get_message_meta(msg_local_id)
        assert msg_meta['timestamp'].isoformat() == timestamp.isoformat()
        assert msg_meta['author'] == pid
        with pytest.raises(ComponentNotFound):
            await cds.get_message_meta('321')


async def test_delete_message(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(Components.PARTICIPANTS, address='test@example.com', permissions=perms.FULL)
        msg_local_id = await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=timestamp,
            body='hello',
        )
        await cds.add_component(Components.MESSAGES, id='m2', author=pid, timestamp=timestamp, body='hello2')

        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 2

        await cds.delete_component(Components.MESSAGES, item_id=msg_local_id)

        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        assert messages[0]['body'] == 'hello2'


async def test_message_locked(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(Components.PARTICIPANTS, address='test@example.com', permissions=perms.FULL)
        msg_local_id = await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=timestamp,
            body='hello',
        )
        await cds.add_component(Components.MESSAGES, id='m2', author=pid, timestamp=timestamp, body='hello2')

        assert (await cds.check_component_locked(Components.MESSAGES, item_id=msg_local_id)) is False

        await cds.lock_component(Components.MESSAGES, item_id=msg_local_id)

        assert (await cds.check_component_locked(Components.MESSAGES, item_id=msg_local_id)) is True

        await cds.unlock_component(Components.MESSAGES, item_id=msg_local_id)

        assert (await cds.check_component_locked(Components.MESSAGES, item_id=msg_local_id)) is False
        with pytest.raises(ComponentNotFound):
            await cds.check_component_locked(Components.MESSAGES, item_id='321')
