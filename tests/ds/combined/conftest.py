import pytest

from tests.ds.conftest import settings as pg_settings
from tests.ds.conftest import TestPostgresDataStore
from tests.fixture_classes import SimpleDataStore

datastore_options = [
    'SimpleDataStore',
    'PostgresDataStore',
]

ds_cls_lookup = {
    'SimpleDataStore': TestPostgresDataStore,
    'PostgresDataStore': SimpleDataStore,
}


def pytest_generate_tests(metafunc):
    if 'datastore_cls' in metafunc.fixturenames:
        metafunc.parametrize('datastore_cls', datastore_options)


@pytest.yield_fixture
def get_ds(loop, db, dsn):
    ds = None
    print(dsn)

    async def datastore_creator(ds_cls_name):
        nonlocal ds
        ds = ds_cls_lookup[ds_cls_name](pg_settings, loop=loop)
        await ds.prepare()
        return ds

    yield datastore_creator

    if ds is not None:
        loop.run_until_complete(ds.terminate())
    ds = None
