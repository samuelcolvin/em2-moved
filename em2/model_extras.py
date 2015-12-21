from sqlalchemy import DateTime, Enum

TIMESTAMPTZ = DateTime(timezone=True)


class RichEnum:
    OPTIONS = None

    @classmethod
    def enum(cls):
        def check_option(at_name):  # pragma: no cover
            if at_name[0] != '_' and at_name != 'OPTIONS' and at_name.upper() == at_name:
                v = getattr(cls, at_name)
                if isinstance(v, str):
                    return v

        cls.OPTIONS = cls.OPTIONS or tuple(filter(bool, map(check_option, dir(cls))))
        return Enum(*cls.OPTIONS, name=cls.__name__.lower())
