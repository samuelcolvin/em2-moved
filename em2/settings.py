from .exceptions import ConfigException


class Settings:
    COMMS_HEAD_REQUEST_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_KEY_TIMEOUT = 86400
    COMMS_PLATFORM_KEY_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY = [-10, 1]

    PG_DATABASE = {
        'drivername': 'postgres',
        'host': 'localhost',
        'port': '5432',
        'username': 'postgres',
        'password': '',
        'database': 'em2',
    }

    REDIS_CONN = {
        'host': 'localhost',
        'port': 6379,
    }

    def __init__(self, **custom_settings):
        for name, value in custom_settings.items():
            if not hasattr(self, name):
                raise ConfigException('{} is not a valid setting name'.format(name))
            setattr(self, name, value)
