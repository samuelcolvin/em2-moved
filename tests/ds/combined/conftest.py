import pytest

from em2 import Settings
from em2.core import Controller

datastore_options = [
    'tests.fixture_classes.SimpleDataStore',
    'tests.ds.conftest.TestPostgresDataStore',
]


def pytest_generate_tests(metafunc):
    if 'datastore_cls' in metafunc.fixturenames:
        metafunc.parametrize('datastore_cls', datastore_options)


@pytest.yield_fixture
def get_ctrl(loop, dsn, db, reset_store):
    ctrl = None
    print(dsn)

    async def ctrl_creator(ds_cls_name):
        nonlocal ctrl
        settings = Settings(
            PG_DATABASE='em2_test',
            DATASTORE_CLS=ds_cls_name,
            PG_POOL_MAXSIZE=4,
            PG_POOL_TIMEOUT=5,
        )
        ctrl = Controller(settings, loop=loop)
        await ctrl.startup()
        return ctrl

    yield ctrl_creator

    if ctrl is not None:
        loop.run_until_complete(ctrl.ds.terminate())
    ctrl = None


@pytest.fixture
def get_ds(get_ctrl):
    async def ds_creator(ds_cls_name):
        ctrl = await get_ctrl(ds_cls_name)
        return ctrl.ds
    return ds_creator
