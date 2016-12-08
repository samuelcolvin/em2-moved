import logging

from em2 import Settings, setup_logging
from em2.core import Action, Components, Controller, Retrieval, RVerbs, Verbs


async def test_basic_conversation(reset_store, loop):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore')
    controller = Controller(settings, loop=loop)
    ds = controller.ds

    action = Action('sender@example.com', None, Verbs.ADD)
    assert str(action) == ('<Action(address=sender@example.com, participant_id=None, perm=None, conv=None, verb=add, '
                           'component=conversations, item=None, timestamp=None, event_id=None, parent_event_id=None)>')
    print('action:', action)
    await controller.act(action, subject='foo bar')
    print(ds)
    assert len(ds.data) == 1
    conv = ds.data[0]
    assert len(conv['participants']) == 1
    assert conv['subject'] == 'foo bar'

    retrieval = Retrieval('sender@example.com', verb=RVerbs.LIST)
    assert str(retrieval) == ('<Retrieval(address=sender@example.com, participant_id=None, conv=None, verb=list, '
                              'component=conversations, is_remote=False)>')
    print('retrieval:', retrieval)
    conversations = await controller.retrieve(retrieval)
    print('retrieved conversations:', conversations)
    assert len(conversations) == 1


async def test_reprs(reset_store, loop):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore')
    controller = Controller(settings, loop=loop)

    print('controller:', controller)
    assert str(controller) == '<Controller(no-domain-set-0x{:x})>'.format(id(controller))

    assert str(controller.conversations).startswith('<Conversations 0x')
    print('conversations:', controller.conversations)

    msgs = controller.components[Components.MESSAGES]
    assert str(msgs).startswith('<Messages on controller ')
    print(msgs)


async def test_logging(reset_store, loop, capsys):
    setup_logging(log_level='DEBUG')
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore')
    controller = Controller(settings, loop=loop)

    action = Action('sender@example.com', None, Verbs.ADD)
    await controller.act(action, subject='foo bar')
    out, err = capsys.readouterr()
    assert out == ''
    assert 'local action by "sender@example.com" - > Components.CONVERSATIONS > Verbs.ADD' in err
    assert 'created draft conversation' in err
    assert 'first participant added to' in err

    logger = logging.getLogger('em2')
    for h in logger.handlers:
        logger.removeHandler(h)
