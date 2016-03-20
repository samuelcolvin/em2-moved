import pytest

from em2.core import Controller
from tests.fixture_classes import SimpleDataStore


@pytest.fixture
def controller():
    ds = SimpleDataStore()
    return Controller(ds)
