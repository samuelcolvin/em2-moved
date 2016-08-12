from datetime import datetime, timezone

from em2.utils import to_unix_ms, from_unix_ms
import msgpack

# unicode clock is small to encode and should be fairly unlikely to clash with another dict key
_DT = '⌚'

MSGPACK_CONTENT_TYPE = 'application/msgpack'


def _encoder(obj):
    if isinstance(obj, datetime):
        return {_DT: to_unix_ms(obj)}
    return obj


class ObjectHook:
    def __init__(self, tz):
        self._tz = tz

    def __call__(self, obj):
        if _DT in obj and len(obj) == 1:
            dt = from_unix_ms(obj[_DT])
            # TODO fix to support ptz dst timezones which don't work with replace()
            return dt.replace(tzinfo=self._tz)
        return obj


def encode(data):
    return msgpack.packb(data, default=_encoder, use_bin_type=True)


def decode(data, tz=timezone.utc):
    return msgpack.unpackb(data, object_hook=ObjectHook(tz), encoding='utf8')
