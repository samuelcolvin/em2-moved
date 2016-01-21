import pytest
import asyncio


def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


def pytest_pyfunc_call(pyfuncitem):
    """
    Run coroutines in an event loop instead of a normal function call.
    """
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        funcargs = pyfuncitem.funcargs
        loop = funcargs.get('loop') or asyncio.get_event_loop()
        testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        loop.run_until_complete(loop.create_task(pyfuncitem.obj(**testargs)))
        return True


@pytest.yield_fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)

    yield loop

    loop.stop()
    loop.run_forever()
    loop.close()
    asyncio.set_event_loop(None)
