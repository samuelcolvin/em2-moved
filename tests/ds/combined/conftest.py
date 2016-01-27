import asyncio
import pytest
from _pytest.python import Function, FuncFixtureInfo
from tests.fixture_classes import SimpleDataStore

pytest_plugins = 'tests.ds.pg.plugin'


def ds_pytest_function(name, node, fix_name):
    fm = node.session._fixturemanager
    names_closure, arg2fixturedefs = fm.getfixtureclosure((fix_name,), node)
    fixtureinfo = FuncFixtureInfo(('get_ds',), names_closure, arg2fixturedefs)
    name = '{}[{}]'.format(name, fix_name.replace('get_ds_', ''))
    return Function(name, parent=node, fixtureinfo=fixtureinfo)


def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        f = list(collector._genfunctions(name, obj))[0]
        if 'get_ds' not in f._fixtureinfo.argnames:
            return [f]
        node = f.parent
        return [
            ds_pytest_function(name, node, 'get_ds_simple'),
            ds_pytest_function(name, node, 'get_ds_postgres'),
        ]


def pytest_pyfunc_call(pyfuncitem):
    """
    modified to cope with the get_ds_* fixture not having the same name as the function
    """
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        loop = pyfuncitem.funcargs.get('loop') or asyncio.new_event_loop()
        asyncio.set_event_loop(None)

        testargs = {arg: pyfuncitem.funcargs.get(arg) for arg in pyfuncitem._fixtureinfo.argnames}
        for name, value in pyfuncitem.funcargs.items():
            if name.startswith('get_ds'):
                testargs['get_ds'] = value
                break
        loop.run_until_complete(loop.create_task(pyfuncitem.obj(**testargs)))

        asyncio.set_event_loop(None)
        return True


@pytest.fixture
def get_ds_simple():
    async def simple_ds_creator():
        return SimpleDataStore()
    return simple_ds_creator
