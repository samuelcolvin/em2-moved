
def get_options(cls):
    options = getattr(cls, 'OPTIONS', None)
    if options:
        return options

    def check_option(at_name):  # pragma: no cover
        if at_name[0] != '_' and at_name != 'OPTIONS' and at_name.upper() == at_name:
            v = getattr(cls, at_name)
            if isinstance(v, str):
                return v

    return tuple(filter(bool, map(check_option, dir(cls))))
