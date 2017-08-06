from arq import DatetimeJob
from arq.utils import from_unix_ms, to_unix_ms  # noqa

MSGPACK_CONTENT_TYPE = 'application/msgpack'


msg_encode = DatetimeJob._encode
msg_decode = DatetimeJob._decode
