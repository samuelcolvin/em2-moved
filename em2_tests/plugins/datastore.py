import inspect

from em2_tests import datastore_tests as tests

test_methods = [obj for n, obj in inspect.getmembers(tests) if n.startswith('test_') and inspect.isfunction(obj)]
test_method_names = [f.__name__ for f in test_methods]


def pytest_generate_tests(metafunc):
    if 'ds_test_method' in metafunc.fixturenames:
        metafunc.parametrize('ds_test_method', test_methods, ids=test_method_names)
