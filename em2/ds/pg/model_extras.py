from sqlalchemy import Enum as _SAEnum
from sqlalchemy import DateTime

from em2.utils import Enum as _EM2Enum

TIMESTAMPTZ = DateTime(timezone=True)


class SAEnum(_EM2Enum):
    @classmethod
    def sa_enum(cls):
        return _SAEnum(*cls.__values__, name=cls.__name__.lower())
