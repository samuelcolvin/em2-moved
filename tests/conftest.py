import pytest
import asyncio
import gc

from em2.base import Controller

from .py_datastore import SimpleDataStore


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):
    """
    Run coroutines in an event loop instead of a normal function call.
    """
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        loop = asyncio.get_event_loop()
        funcargs = pyfuncitem.funcargs
        testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        loop.run_until_complete(asyncio.ensure_future(pyfuncitem.obj(**testargs)))
        return True


@pytest.yield_fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)

    yield loop

    loop.stop()
    loop.run_forever()
    loop.close()
    gc.collect()
    asyncio.set_event_loop(None)


@pytest.fixture
def conversation():
    async def get_conversation():
        ds = SimpleDataStore()
        ctrl = Controller(ds)
        con_id = await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
        return ds, ctrl, con_id
    return get_conversation
