import datetime
from em2.base import Controller, perms
from em2.common import Components
from em2.data_store import DataStore, ConversationDataStore
from em2_tests.fixture_classes import NullPropagator


async def test_datastore_type(data_store):
    assert isinstance(data_store, DataStore)


async def test_create_conversation(data_store):
    controller = Controller(data_store, NullPropagator())
    con_id = await controller.conversations.create('sender@example.com', 'the subject')
    cds = data_store.new_con_ds(con_id)
    assert isinstance(cds, ConversationDataStore)
    props = await cds.get_core_properties()
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
    con_id = await controller.conversations.create('sender@example.com', 'the subject')
    cds = data_store.new_con_ds(con_id)
    participants = await cds.get_all_component_items(Components.PARTICIPANTS)
    assert len(participants) == 1
    p = participants[0]
    assert p['permissions'] == perms.FULL
    assert p['address'] == 'sender@example.com'
    messages = await cds.get_all_component_items(Components.MESSAGES)
    assert len(messages) == 0
