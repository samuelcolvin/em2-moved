from tests.tools.fixture_classes import SimpleDataStore

pytest_plugins = 'tests.tools.plugins.datastore', 'tests.tools.plugins.asyncio'


async def test_simple_datastore(ds_test_method):
    ds = SimpleDataStore()
    await ds_test_method(ds)
