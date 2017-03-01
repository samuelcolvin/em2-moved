from datetime import datetime

import pytest

from em2.core import Retrieval, RVerbs
from em2.exceptions import ComponentNotFound, ConversationNotFound


async def test_list_single_conversation(conversation):
    ds, ctrl, conv_id = await conversation()

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
    ds, ctrl, conv_id = await conversation()

    retrieval = Retrieval('test@example.com', conversation=conv_id)
    data = await ctrl.retrieve(retrieval)
    assert data['creator'] == 'test@example.com'
    assert data['subject'] == 'foo bar'


async def test_get_conversation_does_not_exist(conversation):
    ds, ctrl, conv_id = await conversation()

    retrieval = Retrieval('test@example.com', conversation='doesnt exist')
    with pytest.raises(ConversationNotFound):
        await ctrl.retrieve(retrieval)


async def test_get_conversation_no_participant(conversation):
    ds, ctrl, conv_id = await conversation()

    retrieval = Retrieval('not_test@example.com', conversation=conv_id)
    with pytest.raises(ComponentNotFound):
        await ctrl.retrieve(retrieval)
