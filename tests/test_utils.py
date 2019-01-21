from datetime import datetime, timedelta, timezone

import pytest

from em2 import Settings, create_app
from em2.exceptions import StartupException
from em2.utils import to_utc_naive
from em2.utils.network import _wait_port_open, wait_for_services


def test_wait_for_services(loop):
    settings = Settings()
    wait_for_services(settings)


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


async def test_create_app(settings, aiohttp_client):
    app = create_app(settings)
    cli = await aiohttp_client(app)
    r = await cli.get('/f/')
    assert r.status == 200, await r.text()
    assert 'em2 protocol interface' in await r.text()
    r = await cli.get('/d/')
    assert r.status == 200, await r.text()
    assert 'UI interface' in await r.text()
