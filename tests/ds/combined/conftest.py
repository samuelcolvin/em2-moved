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
def get_ds(loop, db, dsn):
    ctrl = None
    print(dsn)

    async def datastore_creator(ds_cls_name):
        nonlocal ctrl
        settings = Settings(
            PG_DATABASE='em2_test',
            DATASTORE_CLS=ds_cls_name,
            PG_POOL_MAXSIZE=4,
            PG_POOL_TIMEOUT=5,
        )
        ctrl = Controller(settings, loop=loop)
        await ctrl.prepare()
        return ctrl.ds

    yield datastore_creator

    if ctrl is not None:
        loop.run_until_complete(ctrl.ds.terminate())
    ctrl = None
