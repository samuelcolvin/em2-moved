import pytest
from aiopg.sa.engine import _create_engine
from tests.ds.pg.plugin import TestPostgresDataStore
from tests.fixture_classes import SimpleDataStore

pytest_plugins = 'tests.ds.pg.plugin'


def pytest_generate_tests(metafunc):
    if 'datastore_cls' in metafunc.fixturenames:
        datastores = [
            'SimpleDataStore',
            'PostgresDataStore',
        ]
        metafunc.parametrize('datastore_cls', datastores, ids=datastores)


@pytest.yield_fixture
def get_ds(request, loop, db, dsn):
    if request.keywords.get('PostgresDataStore'):
        ds = engine = None

        async def postgres_datastore_creator():
            nonlocal ds, engine
            engine = await _create_engine(dsn, loop=loop, minsize=1, maxsize=4, timeout=5)
            ds = TestPostgresDataStore(engine)
            return ds

        yield postgres_datastore_creator

        async def teardown():
            if ds is not None:
                await ds.terminate()
            if engine is not None:
                engine.close()
                await engine.wait_closed()
        loop.run_until_complete(teardown())
    else:
        msg = 'datastore_cls fixture not included in test {}'
        assert request.keywords.get('SimpleDataStore'), msg.format(request.function.__name__)
        ds = None
        async def simple_ds_creator():
            nonlocal ds
            ds = SimpleDataStore()
            return ds

        yield simple_ds_creator

        ds = None
