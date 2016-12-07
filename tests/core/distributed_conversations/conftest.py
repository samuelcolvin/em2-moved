import pytest

from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from tests.fixture_classes import Network


def create_controller(name, network=None):
    local_domain = name + '.com'
    settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN=local_domain
    )
    ctrl = Controller(settings)
    ctrl.pusher.network = network or Network()
    ctrl.pusher.network.add_node(local_domain, ctrl)
    return ctrl


@pytest.fixture
def two_controllers():
    async def get_controllers():
        ctrl1 = create_controller('ctrl1')
        ctrl2 = create_controller('ctrl2', ctrl1.pusher.network)
        a = Action('user@ctrl1.com', None, Verbs.ADD)
        conv_id = await ctrl1.act(a, subject='the subject', body='the body')
        a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
        await ctrl1.act(a, address='user@ctrl2.com', permissions=perms.WRITE)
        return ctrl1, ctrl2, conv_id
    return get_controllers
