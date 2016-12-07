import pytest

from tests.ds.conftest import settings as pg_settings
from tests.ds.conftest import TestPostgresDataStore
from tests.fixture_classes import SimpleDataStore

datastore_options = [
    'SimpleDataStore',
    'PostgresDataStore',
]


def pytest_generate_tests(metafunc):
    if 'datastore_cls' in metafunc.fixturenames:
        metafunc.parametrize('datastore_cls', datastore_options)


@pytest.yield_fixture
def get_ds(loop, db, dsn):
    pg_ds = False
    ds = None
    print(dsn)

    async def datastore_creator(ds_cls):
        nonlocal pg_ds, ds
        assert ds_cls in datastore_options
        pg_ds = ds_cls == 'PostgresDataStore'
        if pg_ds:
            ds = TestPostgresDataStore(pg_settings, loop)
            await ds.prepare(minsize=1, maxsize=4, timeout=5)
            return ds
        else:
            ds = SimpleDataStore()
            return ds

    yield datastore_creator

    if pg_ds:
        async def teardown():
            if ds is not None:
                await ds.terminate()
        loop.run_until_complete(teardown())
    ds = None
