import pytest


@pytest.fixture
def conversation(controller):
    async def get_conversation():
        con_id = await controller.conversations.create('test@example.com', 'foo bar', 'hi, how are you?')
        return controller.ds, controller, con_id
    return get_conversation
