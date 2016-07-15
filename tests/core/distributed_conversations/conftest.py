import pytest

from em2.core import Controller, Components, perms, Action, Verbs

from tests.fixture_classes import SimpleDataStore, SimplePropagator, Network


def create_controller(name, network=None):
    ds = SimpleDataStore()
    propagator = SimplePropagator()
    propagator.network = network or Network()
    propagator.local_domain = name + '.com'
    ctrl = Controller(ds, propagator, ref=name)
    propagator.network.add_platform(propagator.local_domain, ctrl)
    return ctrl, ds, propagator


@pytest.fixture
def two_controllers():
    async def get_controllers():
        ctrl1, ds1, propagator1 = create_controller('ctrl1')
        ctrl2, ds2, propagator2 = create_controller('ctrl2', propagator1.network)
        a = Action('user@ctrl1.com', None, Verbs.ADD)
        conv_id = await ctrl1.act(a, subject='the subject', body='the body')
        a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
        await ctrl1.act(a, address='user@ctrl2.com', permissions=perms.WRITE)
        return ctrl1, ctrl2, conv_id
    return get_controllers
