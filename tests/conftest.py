import pytest

from em2.base import Controller
from tests.fixture_classes import SimpleDataStore, NullPropagator

pytest_plugins = 'em2_tests.asyncio'


@pytest.fixture
def controller():
    ds = SimpleDataStore()
    return Controller(ds, NullPropagator())
