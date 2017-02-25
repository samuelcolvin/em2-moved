import pytest

from em2 import Settings
from em2.exceptions import StartupException
from em2.utils import _wait_port_open, wait_for_services


def test_wait_for_services(loop):
    settings = Settings()
    wait_for_services(settings, loop=loop)


async def test_port_not_open(loop):
    with pytest.raises(StartupException):
        await _wait_port_open('localhost', 9876, 0.1, loop=loop)
