from collections import OrderedDict
import pytest
from em2.core.utils import Enum, EnumException


def test_basic_enums():
    class Foo(Enum):
        PEAR = 'pear'
        APPLE = 'apple'
        GRAPE = 17
    assert Foo.__values__ == ['pear', 'apple', 17]
    assert Foo.__members__ == OrderedDict([('PEAR', 'pear'), ('APPLE', 'apple'), ('GRAPE', 17)])
    assert Foo.__reverse_members__ == OrderedDict([('pear', 'PEAR'), ('apple', 'APPLE'), (17, 'GRAPE')])
    assert Foo('apple') == 'APPLE'
    assert Foo.get_value('GRAPE') == 17
    assert str(Foo) == 'Foo(PEAR: pear, APPLE: apple, GRAPE: 17)'
    print(Foo)


def test_inheritance():
    class Foo(Enum):
        PEAR = 'pear'
        APPLE = 'apple'
        GRAPE = 17

    class FooBar(Foo):
        pass
    assert FooBar.__values__ == ['pear', 'apple', 17]


def test_multiple_inheritance():
    class Foo(Enum):
        PEAR = 'pear'
        APPLE = 'apple'
        GRAPE = 17

    class FooBar(Foo):
        Fish = 'fish'

    class Spam(FooBar):
        MEAT = 321
    assert Spam.__values__ == ['pear', 'apple', 17, 'fish', 321]


def test_mixin_inheritance():
    class Foo(Enum):
        PEAR = 'pear'
        APPLE = 'apple'
        GRAPE = 17

    class FooBar(Enum):
        Fish = 'fish'

    class Spam(FooBar, Foo, Enum):
        MEAT = 321
    assert Spam.__values__ == ['pear', 'apple', 17, 'fish', 321]


def test_repeat():
    with pytest.raises(EnumException) as excinfo:
        class Foo(Enum):
            PEAR = 'pear'
            APPLE = 'pear'
    assert excinfo.value.args[0] == 'value "pear" of attribute "APPLE" is repeated'
