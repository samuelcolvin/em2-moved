import pytest

from em2.core import Action, Components, Verbs, perms
from em2.exceptions import ConversationNotFound, EventNotFound

from .test_conversations import create_conv


async def test_save_event(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.conn_manager() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        action = Action('test@example.com', '123', Verbs.ADD, Components.PARTICIPANTS, item=pid, timestamp=timestamp)
        action.participant_id, action.perm = pid, perms.FULL
        action.event_id = 'event_1'
        await cds.save_event(action)

        action.event_id = 'event_2'
        await cds.save_event(action, value='foobar')

        # FIXME currently there are no api methods for returning updates and it's therefore not possible to check
        # these actions are saved correctly

        # NOTE: action action.conv_id is ignored in save_event and the cds conv_id is used instead
        cds2 = ds.new_conv_ds('bad', conn)
        action.participant_id, action.perm = pid, perms.FULL
        action.event_id = 'event_3'
        with pytest.raises(ConversationNotFound):
            await cds2.save_event(action)


async def test_get_last_event(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.conn_manager() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        action = Action('test@example.com', '123', Verbs.ADD, Components.MESSAGES, item='msg_id', timestamp=timestamp)
        action.participant_id, action.perm = pid, perms.FULL
        action.event_id = 'event_1'
        await cds.save_event(action)

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_1'
        assert event_timestamp == timestamp

        # go 1, 3, 2 to make sure we're ordering on the commit sequence not event_id
        action.event_id = 'event_3'
        await cds.save_event(action)

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_3'
        assert event_timestamp == timestamp

        action.event_id = 'event_2'
        await cds.save_event(action)

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_2'
        assert event_timestamp == timestamp

        with pytest.raises(EventNotFound):
            await cds.get_item_last_event(Components.PARTICIPANTS, 'foobar')
