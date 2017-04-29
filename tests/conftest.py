import datetime

import aioredis
import pytest
import pytz

from em2 import Settings
from em2.core import Action, Controller, Verbs


def datetime_tz(day=1, month=1, year=2015):
    return pytz.utc.localize(datetime.datetime(year, month, day))


@pytest.fixture
def controller(reset_store, loop):
    settings = Settings(DATASTORE_CLS='tests.fixture_classes.SimpleDataStore')
    return Controller(settings, loop=loop)


@pytest.fixture
def conversation(reset_store, controller):
    async def get_conversation():
        action = Action('test@example.com', None, Verbs.ADD)
        conv_id = await controller.act(action, subject='foo bar', body='hi, how are you?')
        return controller.ds, controller, conv_id
    return get_conversation


@pytest.fixture
def timestamp():
    return datetime_tz()


class TestStore:
    def __init__(self):
        self.data = None

    def __call__(self, name):
        assert self.data is not None, 'test_store not reset, you should use the "reset_store" fixture'
        if name not in self.data:
            self.data[name] = {}
        return self.data[name]


test_store = TestStore()


@pytest.yield_fixture()
def reset_store():
    assert test_store.data is None
    test_store.data = {}

    yield

    test_store.data = None


@pytest.yield_fixture
def get_redis_pool(loop):
    address = 'localhost', 6379
    pool = None

    async def create_pool():
        nonlocal pool
        pool = await aioredis.create_pool(address, loop=loop)
        async with pool.get() as redis:
            await redis.flushall()
        return pool

    yield create_pool

    async def shutdown():
        pool.close()
        await pool.wait_closed()
        await pool.clear()

    if pool and not pool.closed:
        loop.run_until_complete(shutdown())
