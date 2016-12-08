import datetime

import pytest
import pytz


def pytest_addoption(parser):
    parser.addoption('--fast', action='store_true', help="don't run slow tests")


def datetime_tz(day=1, month=1, year=2015):
    return pytz.utc.localize(datetime.datetime(year, month, day))


@pytest.fixture
def timestamp():
    return datetime_tz()


class TestStore:
    def __init__(self):
        self.data = None

    def __call__(self, name):
        assert self.data is not None, 'test_store not reset, you should use the "reset_store" fixture'
        if name not in self.data:
            self.data[name] = {}
        return self.data[name]


test_store = TestStore()


@pytest.yield_fixture()
def reset_store():
    assert test_store.data is None
    test_store.data = {}

    yield

    test_store.data = None
