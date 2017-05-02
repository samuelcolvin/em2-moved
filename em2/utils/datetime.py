from datetime import datetime, timedelta

import pytz


# TODO replace with arq methods
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
