import pytest

from em2.core import Action, Verbs, Components, perms
from em2.exceptions import ConversationNotFound, EventNotFound

from .test_conversations import create_conv


async def test_save_event(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        action = Action('test@example.com', '123', Verbs.ADD, Components.PARTICIPANTS, pid, timestamp)
        action.participant_id, action.perm = pid, perms.FULL
        await cds.save_event('event_1', action, {})

        await cds.save_event('event_2', action, {'value': 'foobar'})

        # FIXME currently there are no api methods for returning updates and it's therefore not possible to check
        # these actions are saved correctly

        # NOTE: action action.conv_id is ignored in save_event and the cds conv_id is used instead
        cds2 = ds.new_conv_ds('bad', conn)
        action.participant_id, action.perm = pid, perms.FULL
        with pytest.raises(ConversationNotFound):
            await cds2.save_event('event_3', action, {})


async def test_get_last_event(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        action = Action('test@example.com', '123', Verbs.ADD, Components.MESSAGES, 'msg_id', timestamp)
        action.participant_id, action.perm = pid, perms.FULL
        await cds.save_event('event_1', action, {})

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_1'
        assert event_timestamp == timestamp

        # go 1, 3, 2 to make sure we're ordering on the commit sequence not event_id
        await cds.save_event('event_3', action, {})

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_3'
        assert event_timestamp == timestamp

        await cds.save_event('event_2', action, {})

        event_id, event_timestamp = await cds.get_item_last_event(Components.MESSAGES, 'msg_id')
        assert event_id == 'event_2'
        assert event_timestamp == timestamp

        with pytest.raises(EventNotFound):
            await cds.get_item_last_event(Components.PARTICIPANTS, 'foobar')
