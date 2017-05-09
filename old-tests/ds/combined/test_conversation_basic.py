import datetime

from em2.core import Action, Components, Verbs, perms
from em2.ds import ConversationDataStore, DataStore


async def test_datastore_type(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    assert isinstance(ds, DataStore)


async def test_create_conversation(get_ctrl, datastore_cls):
    controller = await get_ctrl(datastore_cls)
    async with controller.ds.conn_manager() as conn:
        action = Action('sender@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='the subject')
        cds = controller.ds.new_conv_ds(conv_id, conn)
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


async def test_create_conversation_check_participants(get_ctrl, datastore_cls):
    controller = await get_ctrl(datastore_cls)
    async with controller.ds.conn_manager() as conn:
        action = Action('sender@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='the subject')
        cds = controller.ds.new_conv_ds(conv_id, conn)
        participants = [p async for p in cds.get_all_component_items(Components.PARTICIPANTS)]
        assert len(participants) == 1
        p = participants[0]
        assert p['permissions'] == perms.FULL
        assert p['address'] == 'sender@example.com'
        messages = [m async for m in cds.get_all_component_items(Components.MESSAGES)]
        assert len(messages) == 0


async def test_create_conversation_body(get_ctrl, datastore_cls):
    controller = await get_ctrl(datastore_cls)
    async with controller.ds.conn_manager() as conn:
        action = Action('sender@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='the subject', body='the body', ref='conv-ref')
        cds = controller.ds.new_conv_ds(conv_id, conn)
        messages = [m async for m in cds.get_all_component_items(Components.MESSAGES)]
        assert len(messages) == 1
        message = messages[0]
        message = dict(message)
        assert isinstance(message['timestamp'], datetime.datetime)
        assert message['body'] == 'the body'
        assert message['parent'] is None

        data = await cds.export()
        assert data['status'] == 'draft'
        assert data['creator'] == 'sender@example.com'
        assert len(data['participants']) == 1
        assert len(data['messages']) == 1
