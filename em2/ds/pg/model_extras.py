from sqlalchemy import DateTime, Enum as _SAEnum
from em2.core.enums import Enum as _EM2Enum

TIMESTAMPTZ = DateTime(timezone=True)


class SAEnum(_EM2Enum):
    @classmethod
    def sa_enum(cls):
        return _SAEnum(*cls.__values__, name=cls.__name__.lower())
