from datetime import datetime

from em2.utils import to_unix_ms, from_unix_ms
import msgpack

# unicode clock is small to encode and should be fairly unlikely to clash with another dict key
_DT = '⌚'

MSGPACK_CONTENT_TYPE = 'application/msgpack'


def _encoder(obj):
    if isinstance(obj, datetime):
        return {_DT: to_unix_ms(obj)}
    return obj


def _object_hook(obj):
    if _DT in obj and len(obj) == 1:
        return from_unix_ms(obj[_DT])
    return obj


def encode(data):
    return msgpack.packb(data, default=_encoder, use_bin_type=True)


def decode(data):
    return msgpack.unpackb(data, object_hook=_object_hook, encoding='utf8')
