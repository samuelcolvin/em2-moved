import pytest

from em2.core import Action, Verbs


@pytest.fixture
def conversation(controller):
    async def get_conversation():
        action = Action('test@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='foo bar', body='hi, how are you?')
        return controller.ds, controller, conv_id
    return get_conversation
