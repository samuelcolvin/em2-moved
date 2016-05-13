from collections import OrderedDict
from datetime import datetime, timedelta

import pytz


class EnumException(Exception):
    pass


class EnumMeta(type):
    __doc__ = 'Enumeration'
    __reverse_members__ = None
    __members__ = None
    __values__ = None

    @classmethod
    def __prepare__(mcs, *args, **kwargs):
        return OrderedDict()

    def __new__(mcs, cls, bases, classdict):
        member_list = []
        for base in reversed(bases):
            if issubclass(base, Enum) and base != Enum:
                member_list.extend(base.__reverse_members__.items())

        r_members = OrderedDict(member_list)
        for k, v in classdict.items():
            if k[0] != '_' and isinstance(v, (int, str)):
                if v in r_members:
                    raise EnumException('value "{}" of attribute "{}" is repeated'.format(v, k))
                r_members[v] = k
        classdict.update(
            __reverse_members__=r_members,
            __members__=OrderedDict([(v, k) for k, v in r_members.items()]),
            __values__=list(r_members.keys()),
        )
        return super().__new__(mcs, cls, bases, classdict)

    def __call__(cls, value):
        return cls.__reverse_members__.get(value)

    def __repr__(cls):
        return '{}({})'.format(cls.__name__, ', '.join('{}: {}'.format(a, v) for a, v in cls.__members__.items()))


class Enum(metaclass=EnumMeta):
    """
    Enumeration implementation similar to the stdlib enum.Enum but without the frustrating "value" logic which
    means calling Foobar.FOO.value to get the value of Foobar.FOO.

    Also forces unique like the @unique decorator, allows inheritance and has a simpler __member__ interface.
    """

    @classmethod
    def get_attr(cls, value):
        return cls(value)

    @classmethod
    def get_value(cls, attr):
        return cls.__members__.get(attr)


_EPOCH = datetime(1970, 1, 1)
_EPOCH_TZ = datetime(1970, 1, 1, tzinfo=pytz.utc)


def to_unix_timestamp(dt):
    epoch = _EPOCH if dt.tzinfo is None else _EPOCH_TZ
    return int((dt - epoch).total_seconds())


def from_unix_timestamp(ts):
    return _EPOCH + timedelta(seconds=ts)
