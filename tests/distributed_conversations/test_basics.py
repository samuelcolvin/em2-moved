# import datetime
#
# import hashlib
# from em2.base import Controller, Action, Verbs, Components, perms
# from tests.fixtures_classes import SimpleDataStore, NullPropagator
# from .fixture_classes import SimplePropagator
#
#
# async def test_create_basic_conversation():
#     ds = SimpleDataStore()
#     ctrl = Controller(ds, NullPropagator())
#     await ctrl.conversations.create('sender@example.com', 'foo bar')
#     assert len(ds.data) == 1
#     con = ds.data['0']
#     assert len(con['participants']) == 1
#     assert len(con['updates']) == 0
#     assert con['creator'] == 'sender@example.com'
#     assert con['status'] == 'draft'
#     assert con['subject'] == 'foo bar'
#     assert isinstance(con['timestamp'], datetime.datetime)
#     hash_data = bytes('sender@example.com_{}_foo bar'.format(con['timestamp'].isoformat()), 'utf8')
#     hash_result = hashlib.sha256(hash_data).hexdigest()
#     assert con['global_id'] == hash_result
#
#
# async def test_create_conversation_two_platforms():
#     ds = SimpleDataStore()
#     propagator = SimplePropagator()
#     ctrl = Controller(ds, propagator)
#     other_ds = SimpleDataStore()
#     remove_ctrl = Controller(other_ds, NullPropagator())
#     propagator.add_platform('@remote.com', remove_ctrl)
#     con_id = await ctrl.conversations.create('sender@local.com', 'foo bar')
#
#     assert len(ds.data['0']['participants']) == 1
#     a = Action('sender@local.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
#     await ctrl.act(a, email='receiver@remote.com', permissions=perms.WRITE)
#     assert len(ds.data['0']['participants']) == 2
#     print(other_ds)
