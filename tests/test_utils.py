from em2.utils import get_options


class Foo:
    APPLE = 'apple'
    PEAR = 'pear'
    GRAPE = 17


class Bar:
    APPLE = 'apple'
    PEAR = 'pear'
    OPTIONS = ('first', 'second')


def test_non_str_options():
    assert get_options(Foo) == ('apple', 'pear')


def test_existing_options():
    assert get_options(Bar) == ('first', 'second')
