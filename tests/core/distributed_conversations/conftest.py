import pytest

from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from tests.fixture_classes import Network


async def create_controller(name, loop, redis_db, network):
    local_domain = name + '.com'
    settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN=local_domain,
        R_DATABASE=redis_db,
    )
    ctrl = Controller(settings, loop=loop)
    ctrl.pusher.network = network
    network.add_node(local_domain, ctrl)
    await ctrl.pusher.startup()
    return ctrl


@pytest.yield_fixture
def two_controllers(reset_store, loop):
    ctrl1, ctrl2 = None, None

    async def get_controllers():
        nonlocal ctrl1, ctrl2
        network = Network()
        ctrl1 = await create_controller('ctrl1', loop, 1, network)
        ctrl2 = await create_controller('ctrl2', loop, 2, network)
        a = Action('user@ctrl1.com', None, Verbs.ADD)
        conv_id = await ctrl1.act(a, subject='the subject', body='the body')
        a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
        await ctrl1.act(a, address='user@ctrl2.com', permissions=perms.WRITE)
        return ctrl1, ctrl2, conv_id

    yield get_controllers

    async def shutdown():
        async with await ctrl1.pusher.get_redis_conn() as redis:
            await redis.flushall()
        await ctrl1.pusher.close()
        await ctrl2.pusher.close()

    if ctrl1:
        loop.run_until_complete(shutdown())
