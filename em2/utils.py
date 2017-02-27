import asyncio
import logging
import sys
from datetime import datetime, timedelta
from enum import Enum as _PyEnum
from enum import EnumMeta as _PyEnumMeta
from enum import unique

import pytz
from async_timeout import timeout

from em2 import VERSION, Settings
from .exceptions import StartupException

logger = logging.getLogger('em2.utils')


class EnumMeta(_PyEnumMeta):
    def __new__(mcs, cls, bases, classdict):
        enum_class = super(EnumMeta, mcs).__new__(mcs, cls, bases, classdict)
        enum_class.members_set = {v.value for v in enum_class.__members__.values()}
        enum_class.members_display = ', '.join(str(v.value) for v in enum_class.__members__.values())
        return enum_class


@unique
class Enum(str, _PyEnum, metaclass=EnumMeta):
    pass


_EPOCH = datetime(1970, 1, 1)
_EPOCH_TZ = datetime(1970, 1, 1, tzinfo=pytz.utc)


def to_unix_ms(dt):
    utcoffset = dt.utcoffset()
    if utcoffset is not None:
        utcoffset = utcoffset.total_seconds()
        secs = (dt - _EPOCH_TZ).total_seconds() + utcoffset
    else:
        secs = (dt - _EPOCH).total_seconds()
    return int(secs * 1000)


def from_unix_ms(ms):
    return _EPOCH + timedelta(seconds=ms / 1000)


def now_unix_secs():
    return int((datetime.utcnow() - _EPOCH).total_seconds())


def now_unix_ms():
    return to_unix_ms(datetime.utcnow())


async def _wait_port_open(host, port, delay, loop):
    step_size = 0.05
    steps = int(delay / step_size)
    start = loop.time()
    for i in range(steps):
        try:
            with timeout(step_size, loop=loop):
                await loop.create_connection(lambda: asyncio.Protocol(), host=host, port=port)
        except TimeoutError:
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
    from aiohttp import ClientSession
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


async def _list_conversations(settings, loop, logger):
    ds = settings.datastore_cls(settings=settings, loop=loop)
    await ds.startup()
    logger.info('Conversations:')
    try:
        c = 0
        async for conv in ds.all_conversations():
            conv_id = conv.pop('conv_id')
            logger.info(f'  id={conv_id:.6} ' + ' '.join(f'{k}="{str(v):.40}"' for k, v in sorted(conv.items())))
            c += 1
        logger.info(f'total {c} conversations')
    finally:
        await ds.shutdown()


def info(settings, logger):
    import aiohttp
    import arq
    logger.info(f'em2')
    logger.info(f'Python:   {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    logger.info(f'em2:      {VERSION}')
    logger.info(f'aiohttp:  {aiohttp.__version__}')
    logger.info(f'arq:      {arq.VERSION}\n')
    logger.info(f'domain:   {settings.LOCAL_DOMAIN}')
    logger.info(f'pg db:    {settings.PG_DATABASE}')
    logger.info(f'redis db: {settings.R_DATABASE}\n')
    try:
        loop = asyncio.get_event_loop()
        from em2.ds.pg.utils import check_database_exists
        wait_for_services(settings, loop=loop)
        check_database_exists(settings)

        loop.run_until_complete(_list_conversations(settings, loop, logger))
    except Exception as e:
        logger.warning(f'Error get conversation list {e.__class__.__name__}: {e}')
