import pytest

from em2.core import Controller, Components, perms, Action, Verbs

from tests.fixture_classes import SimpleDataStore, SimplePusher, Network


def create_controller(name, network=None):
    ds = SimpleDataStore()
    pusher = SimplePusher()
    pusher.network = network or Network()
    pusher.local_domain = name + '.com'
    ctrl = Controller(ds, pusher, ref=name)
    pusher.network.add_node(pusher.local_domain, ctrl)
    return ctrl, ds, pusher


@pytest.fixture
def two_controllers():
    async def get_controllers():
        ctrl1, ds1, pusher1 = create_controller('ctrl1')
        ctrl2, ds2, pusher2 = create_controller('ctrl2', pusher1.network)
        a = Action('user@ctrl1.com', None, Verbs.ADD)
        conv_id = await ctrl1.act(a, subject='the subject', body='the body')
        a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
        await ctrl1.act(a, address='user@ctrl2.com', permissions=perms.WRITE)
        return ctrl1, ctrl2, conv_id
    return get_controllers
