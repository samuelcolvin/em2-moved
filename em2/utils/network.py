import asyncio
import logging

from aiohttp import ClientSession
from async_timeout import timeout

from em2 import Settings
from em2.exceptions import StartupException

logger = logging.getLogger('em2.utils')


async def _wait_port_open(host, port, delay, loop):
    step_size = 0.05
    steps = int(delay / step_size)
    start = loop.time()
    for i in range(steps):
        try:
            with timeout(step_size, loop=loop):
                await loop.create_connection(lambda: asyncio.Protocol(), host=host, port=port)
        except asyncio.TimeoutError:
            pass
        except OSError:
            await asyncio.sleep(step_size, loop=loop)
        else:
            logger.info('Connected successfully to %s:%s after %0.2fs', host, port, loop.time() - start)
            return
    raise StartupException(f'Unable to connect to {host}:{port} after {loop.time() - start:0.2f}s')


def wait_for_services(settings, *, delay=5, loop=None):
    """
    Wait for up to `delay` seconds for postgres and redis ports to be open
    """
    loop = loop or asyncio.get_event_loop()
    coros = [
        _wait_port_open(settings.PG_HOST, settings.PG_PORT, delay, loop),
        _wait_port_open(settings.R_HOST, settings.R_PORT, delay, loop),
    ]
    logger.info('waiting for postgres and redis to come up...')
    loop.run_until_complete(asyncio.gather(*coros, loop=loop))


async def check_server(settings: Settings, expected_status=200):
    url = f'http://127.0.0.1:{settings.WEB_PORT}/'
    try:
        async with ClientSession() as session:
            async with session.get(url) as r:
                assert r.status == expected_status, f'response error {r.status} != {expected_status}'
    except (ValueError, AssertionError, OSError) as e:
        logger.error('web check error: %s: %s, url: "%s"', e.__class__.__name__, e, url)
        return 1
    else:
        logger.info('web check successful "%s", response %d', url, expected_status)
        return 0
