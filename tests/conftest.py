import datetime
import asyncio
import pytest
import pytz


def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


def pytest_pyfunc_call(pyfuncitem):
    """
    Run coroutines in an event loop instead of a normal function call.
    """
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        _loop = pyfuncitem.funcargs.get('loop') or asyncio.new_event_loop()
        asyncio.set_event_loop(None)

        testargs = {arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        _loop.run_until_complete(_loop.create_task(pyfuncitem.obj(**testargs)))

        asyncio.set_event_loop(None)
        return True


@pytest.yield_fixture
def loop():
    _loop = asyncio.new_event_loop()

    yield _loop

    _loop.stop()
    _loop.run_forever()
    _loop.close()


def datetime_tz(day=1, month=1, year=2015):
    return pytz.utc.localize(datetime.datetime(year, month, day))


@pytest.fixture
def timestamp():
    return datetime_tz()
