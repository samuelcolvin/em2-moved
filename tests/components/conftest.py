import pytest

from em2.base import Controller
from tests.fixture_classes import SimpleDataStore, NullPropagator


@pytest.fixture
def conversation():
    async def get_conversation():
        ds = SimpleDataStore()
        ctrl = Controller(ds, NullPropagator())
        con_id = await ctrl.conversations.create('test@example.com', 'foo bar', 'hi, how are you?')
        return ds, ctrl, con_id
    return get_conversation
