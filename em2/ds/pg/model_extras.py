from sqlalchemy import Enum as _SAEnum
from sqlalchemy import DateTime

from em2.utils import Enum

TIMESTAMPTZ = DateTime(timezone=True)


def sa_enum(enum: Enum):
    return _SAEnum(*enum.members_set, name=enum.__name__.lower())
