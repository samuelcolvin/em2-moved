import datetime

from em2.core import Controller, Components, perms, DataStore, ConversationDataStore

from tests.fixture_classes import NullPropagator


async def test_datastore_type(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    assert isinstance(ds, DataStore)


async def test_create_conversation(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    controller = Controller(ds, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject')
    async with ds.reuse_connection() as conn:
        cds = ds.new_conv_ds(conv_id, conn)
        assert isinstance(cds, ConversationDataStore)
        props = await cds.get_core_properties()
        props = dict(props)
        ts = props.pop('timestamp')
        assert isinstance(ts, datetime.datetime)
        assert props == {
            'subject': 'the subject',
            'creator': 'sender@example.com',
            'status': 'draft',
            'ref': 'the subject',
            'expiration': None,
        }


async def test_create_conversation_check_participants(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    controller = Controller(ds, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject')
    async with ds.reuse_connection() as conn:
        cds = ds.new_conv_ds(conv_id, conn)
        participants = await cds.get_all_component_items(Components.PARTICIPANTS)
        assert len(participants) == 1
        p = participants[0]
        assert p['permissions'] == perms.FULL
        assert p['address'] == 'sender@example.com'
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 0


async def test_create_conversation_body(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    controller = Controller(ds, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject', 'the body', 'conv-ref')
    async with ds.reuse_connection() as conn:
        cds = ds.new_conv_ds(conv_id, conn)
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        message = messages[0]
        message = dict(message)
        assert isinstance(message['timestamp'], datetime.datetime)
        assert message['body'] == 'the body'
        assert message['parent'] is None
