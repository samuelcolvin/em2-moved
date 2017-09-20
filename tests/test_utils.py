from datetime import datetime, timedelta, timezone

import pytest

from em2 import Settings
from em2.exceptions import StartupException
from em2.utils import to_utc_naive
from em2.utils.network import _wait_port_open, wait_for_services


def test_wait_for_services(loop):
    settings = Settings()
    wait_for_services(settings, loop=loop)


async def test_port_not_open(loop):
    with pytest.raises(StartupException):
        await _wait_port_open('localhost', 9876, 0.1, loop=loop)


@pytest.mark.parametrize('input, output', [
    (datetime(2032, 1, 1, 12, 0), datetime(2032, 1, 1, 12, 0)),
    (datetime(2032, 1, 1, 12, 0, tzinfo=timezone.utc), datetime(2032, 1, 1, 12, 0)),
    (datetime(2032, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=1))), datetime(2032, 1, 1, 11, 0)),
    (datetime(2032, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=-1))), datetime(2032, 1, 1, 13, 0)),
])
def test_to_utc_naive(input, output):
    assert to_utc_naive(input) == output
