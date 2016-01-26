import datetime
from em2.core.base import Controller, perms
from em2.core.common import Components
from em2.core.data_store import DataStore, ConversationDataStore
from tests.tools.fixture_classes import NullPropagator


async def test_datastore_type(data_store):
    assert isinstance(data_store, DataStore)


async def test_create_conversation(data_store):
    controller = Controller(data_store, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject')
    async with data_store.reuse_connection() as conn:
        cds = data_store.new_conv_ds(conv_id, conn)
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


async def test_create_conversation_check_participants(data_store):
    controller = Controller(data_store, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject')
    async with data_store.reuse_connection() as conn:
        cds = data_store.new_conv_ds(conv_id, conn)
        participants = await cds.get_all_component_items(Components.PARTICIPANTS)
        assert len(participants) == 1
        p = participants[0]
        assert p['permissions'] == perms.FULL
        assert p['address'] == 'sender@example.com'
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 0


async def test_create_conversation_body(data_store):
    controller = Controller(data_store, NullPropagator())
    conv_id = await controller.conversations.create('sender@example.com', 'the subject', 'the body', 'conv-ref')
    async with data_store.reuse_connection() as conn:
        cds = data_store.new_conv_ds(conv_id, conn)
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        message = messages[0]
        message = dict(message)
        assert isinstance(message['timestamp'], datetime.datetime)
        assert message['body'] == 'the body'
        assert message['parent'] is None
