import asyncio
from datetime import datetime, timedelta
from enum import Enum as _PyEnum
from enum import EnumMeta as _PyEnumMeta
from enum import unique

import pytz

from em2.settings import Settings


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


class BaseServiceCls:
    def __init__(self, settings: Settings, *, loop: asyncio.AbstractEventLoop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        super().__init__(**kwargs)
