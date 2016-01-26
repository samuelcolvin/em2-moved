import inspect

from tests.tools import datastore_tests as tests


def function_name(f):
    v = 'datastore_tests'
    mod = f.__module__[f.__module__.index(v) + len(v) + 1:]
    return '{}.{}'.format(mod, f.__name__)

test_methods = [obj for n, obj in inspect.getmembers(tests) if n.startswith('test_') and inspect.isfunction(obj)]
test_method_names = [function_name(f) for f in test_methods]


def pytest_generate_tests(metafunc):
    if 'ds_test_method' in metafunc.fixturenames:
        metafunc.parametrize('ds_test_method', test_methods, ids=test_method_names)
