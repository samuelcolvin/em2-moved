import pytest

from em2.core.base import Controller
from tests.fixture_classes import SimpleDataStore, NullPropagator


@pytest.fixture
def controller():
    ds = SimpleDataStore()
    return Controller(ds, NullPropagator())
