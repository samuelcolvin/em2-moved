import datetime

import pytest
import pytz

pytest_plugins = 'arq.testing'


def pytest_addoption(parser):
    parser.addoption('--fast', action='store_true', help="don't run slow tests")


def datetime_tz(day=1, month=1, year=2015):
    return pytz.utc.localize(datetime.datetime(year, month, day))


@pytest.fixture
def timestamp():
    return datetime_tz()
