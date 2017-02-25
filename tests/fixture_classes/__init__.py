# flake8: noqa
from asyncio import Future

from .authenicator import (SimpleAuthenticator, RedisMockDNSAuthenticator, PLATFORM, TIMESTAMP, VALID_SIGNATURE,
                           get_private_key)
from .datastore import SimpleDataStore
from .push import SimplePusher, Network, FixedSimpleAuthenticator


def future_result(loop, result):
    r = Future(loop=loop)
    r.set_result(result)
    return r
