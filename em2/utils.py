import asyncio
import logging
import sys
from datetime import datetime, timedelta
from enum import Enum as _PyEnum
from enum import EnumMeta as _PyEnumMeta
from enum import unique

import pytz

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
    for i in range(steps):
        try:
            await loop.create_connection(lambda: asyncio.Protocol(), host=host, port=port)
        except OSError:
            await asyncio.sleep(delay, loop=loop)
        else:
            logger.info('Connected successfully to %s:%s after %0.2fs', host, port, delay * i)
            return
    raise StartupException(f'Unable to connect to {host}:{port} after {steps * delay}s')


def wait_for_services(settings, *, delay=10, loop=None):
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


async def _list_conversations(settings, loop):
    ds = settings.datastore_cls(settings=settings, loop=loop)
    await ds.startup()
    v = ['Conversations:']
    try:
        async for conv in ds.all_conversations():
            items = sorted(conv.items())
            v.append('  ' + ' '.join(f'{k}={v}' for k, v in items))
        v.append(f'total {len(v) - 1} conversations')
    finally:
        await ds.shutdown()
    return v


def info(settings):
    import aiohttp
    import arq
    v = [
        f'em2',
        f'Python:   {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        f'em2:      {VERSION}',
        f'aiohttp:  {aiohttp.__version__}',
        f'arq:      {arq.VERSION}\n',
        f'domain:   {settings.LOCAL_DOMAIN}',
        f'pg db:    {settings.PG_DATABASE}',
        f'redis db: {settings.R_DATABASE}\n',
    ]
    loop = asyncio.get_event_loop()
    v += loop.run_until_complete(_list_conversations(settings, loop))
    return '\n'.join(v)
