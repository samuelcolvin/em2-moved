import pytest
from aiopg.sa.engine import _create_engine
from tests.ds.pg.plugin import TestPostgresDataStore
from tests.fixture_classes import SimpleDataStore

pytest_plugins = 'tests.ds.pg.plugin'

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
    ds = engine = None

    async def datastore_creator(ds_cls):
        nonlocal pg_ds, ds, engine
        assert ds_cls in datastore_options
        pg_ds = ds_cls == 'PostgresDataStore'
        if pg_ds:
            engine = await _create_engine(dsn, loop=loop, minsize=1, maxsize=4, timeout=5)
            ds = TestPostgresDataStore(engine)
            return ds
        else:
            ds = SimpleDataStore(auto_create_users=False)
            return ds

    yield datastore_creator

    if pg_ds:
        async def teardown():
            if ds is not None:
                await ds.terminate()
            if engine is not None:
                engine.close()
                await engine.wait_closed()
        loop.run_until_complete(teardown())
    ds = engine = None
