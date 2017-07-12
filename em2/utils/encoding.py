from datetime import datetime

import msgpack
from arq.utils import from_unix_ms, to_unix_ms

# unicode clock is small to encode and should be fairly unlikely to clash with another dict key
_DT = '⌚'

MSGPACK_CONTENT_TYPE = 'application/msgpack'


def _encode(obj):
    if isinstance(obj, datetime):
        return {_DT: to_unix_ms(obj)}
    return obj


def _decode(obj):
    if _DT in obj and len(obj) == 1:
        return from_unix_ms(obj[_DT])
    return obj


def msg_encode(data):
    return msgpack.packb(data, default=_encode, use_bin_type=True)


def msg_decode(data):
    return msgpack.unpackb(data, object_hook=_decode, encoding='utf8')
