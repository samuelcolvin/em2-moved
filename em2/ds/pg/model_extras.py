from sqlalchemy import DateTime, Enum
from em2.utils import get_options

TIMESTAMPTZ = DateTime(timezone=True)


class RichEnum:
    OPTIONS = None

    @classmethod
    def enum(cls):
        cls.OPTIONS = get_options(cls)
        return Enum(*cls.OPTIONS, name=cls.__name__.lower())
