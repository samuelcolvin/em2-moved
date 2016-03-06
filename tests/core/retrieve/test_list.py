from datetime import datetime

from em2.core import Controller, Action, Verbs, Retrieval, RVerbs
from tests.fixture_classes import SimpleDataStore, NullPropagator


async def test_list_single_conversation():
    ds = SimpleDataStore(False)
    user_id = await ds.create_user(None, 'sender@example.com')
    assert user_id == 0

    controller = Controller(ds, NullPropagator())
    action = Action('sender@example.com', None, Verbs.ADD)
    await controller.act(action, subject='foo bar')
    assert len(ds.data) == 1

    retrieval = Retrieval('sender@example.com', verb=RVerbs.LIST)
    conversations = await controller.retrieve(retrieval)
    assert len(conversations) == 1

    assert isinstance(conversations[0].pop('timestamp'), datetime)
    assert isinstance(conversations[0].pop('conv_id'), str)

    assert conversations[0] == {
        'ref': 'foo bar',
        'status': 'draft',
        'creator': 'sender@example.com',
        'expiration': None,
        'subject': 'foo bar'
    }
