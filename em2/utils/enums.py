from enum import Enum as _PyEnum
from enum import EnumMeta as _PyEnumMeta
from enum import unique


class EnumMeta(_PyEnumMeta):
    def __new__(mcs, cls, bases, classdict):
        enum_class = super(EnumMeta, mcs).__new__(mcs, cls, bases, classdict)
        enum_class.members_set = {v.value for v in enum_class.__members__.values()}
        enum_class.members_display = ', '.join(str(v.value) for v in enum_class.__members__.values())
        return enum_class


@unique
class Enum(str, _PyEnum, metaclass=EnumMeta):
    pass
