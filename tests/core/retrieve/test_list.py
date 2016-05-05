from datetime import datetime

from em2.core import Retrieval, RVerbs


async def test_list_single_conversation(conversation):
    ds, ctrl, con_id = await conversation()

    retrieval = Retrieval('test@example.com', verb=RVerbs.LIST)
    conversations = await ctrl.retrieve(retrieval)
    assert len(conversations) == 1

    assert isinstance(conversations[0].pop('timestamp'), datetime)
    assert isinstance(conversations[0].pop('conv_id'), str)

    assert conversations[0] == {
        'ref': 'foo bar',
        'status': 'draft',
        'creator': 'test@example.com',
        'expiration': None,
        'subject': 'foo bar'
    }


async def test_get_conversation(conversation):
    ds, ctrl, con_id = await conversation()

    retrieval = Retrieval('test@example.com', conversation=con_id)
    data = await ctrl.retrieve(retrieval)
    assert data['creator'] == 'test@example.com'
    assert data['subject'] == 'foo bar'
