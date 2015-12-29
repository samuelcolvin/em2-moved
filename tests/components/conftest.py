import pytest

from em2.base import Controller
from tests.py_datastore import SimpleDataStore


@pytest.fixture
def conversation():
    async def get_conversation():
        ds = SimpleDataStore()
        ctrl = Controller(ds)
        con_id = await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
        return ds, ctrl, con_id
    return get_conversation
