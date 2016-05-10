from .core.exceptions import ConfigException


class Settings:
    COMMS_REQUEST_HEAD_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_CACHE_TIMEOUT = 86400

    PG_DATABASE = {
        'drivername': 'postgres',
        'host': 'localhost',
        'port': '5432',
        'username': 'postgres',
        'password': '',
        'database': 'em2',
    }

    def __init__(self, **custom_settings):
        for name, value in custom_settings.items():
            if not hasattr(self, name):
                ConfigException('{} is not a valid setting name'.format(name))
            setattr(self, name, value)
