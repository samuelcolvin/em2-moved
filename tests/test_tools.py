from em2_tests.fixture_classes import SimpleDataStore

pytest_plugins = 'em2_tests.plugins.datastore', 'em2_tests.plugins.asyncio'


async def test_simple_datastore(ds_test_method):
    ds = SimpleDataStore()
    await ds_test_method(ds)
