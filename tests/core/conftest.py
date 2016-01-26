import pytest

from em2.core.base import Controller
from tests.tools.fixture_classes import SimpleDataStore, NullPropagator

pytest_plugins = 'tests.tools.plugins.asyncio'


@pytest.fixture
def controller():
    ds = SimpleDataStore()
    return Controller(ds, NullPropagator())
