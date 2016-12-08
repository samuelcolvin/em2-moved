import pytest

from em2 import Settings
from em2.core import Action, Controller, Verbs


@pytest.fixture
def controller(reset_store, loop):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore')
    return Controller(settings, loop=loop)


@pytest.fixture
def conversation(reset_store, controller):
    async def get_conversation():
        action = Action('test@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='foo bar', body='hi, how are you?')
        return controller.ds, controller, conv_id
    return get_conversation
