import pytest

from em2_tests.fixture_classes import SimpleDataStore, NullPropagator
from em2.base import Controller

pytest_plugins = 'em2_tests.plugins.asyncio'


@pytest.fixture
def controller():
    ds = SimpleDataStore()
    return Controller(ds, NullPropagator())
