from em2.core import Controller, Action, Verbs, Retrieval, RVerbs, Components
from tests.fixture_classes import SimpleDataStore, NullPropagator


async def test_basic_conversation():
    ds = SimpleDataStore()
    controller = Controller(ds, NullPropagator())

    action = Action('sender@example.com', None, Verbs.ADD)
    assert str(action) == ('<Action(address=sender@example.com, participant_id=None, perm=None, conv=None, verb=add, '
                           'component=conversations, item=None, timestamp=None, event_id=None, parent_event_id=None)>')
    print('action:', action)
    await controller.act(action, subject='foo bar')
    print(ds)
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert con['subject'] == 'foo bar'

    retrieval = Retrieval('sender@example.com', verb=RVerbs.LIST)
    assert str(retrieval) == ('<Retrieval(address=sender@example.com, participant_id=None, conv=None, verb=list, '
                              'component=conversations, is_remote=False)>')
    print('retrieval:', retrieval)
    conversations = await controller.retrieve(retrieval)
    print('retrieved conversations:', conversations)
    assert len(conversations) == 1


async def test_reprs():
    ds = SimpleDataStore()
    controller = Controller(ds, NullPropagator())

    assert str(controller) == '<Controller(0x{:x})>'.format(id(controller))
    print('controller:', controller)

    assert str(controller.conversations).startswith('<Conversations 0x')
    print('conversations:', controller.conversations)

    msgs = controller.components[Components.MESSAGES]
    assert str(msgs).startswith('<Messages on controller ')
    print(msgs)
