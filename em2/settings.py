from .exceptions import ConfigException


class Settings:
    COMMS_HEAD_REQUEST_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_KEY_TIMEOUT = 86400
    COMMS_PLATFORM_KEY_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY = [-10, 1]
    COMMS_HTTP_TIMEOUT = 4

    PG_HOST = 'localhost'
    PG_PORT = '5432'
    PG_USER = 'postgres'
    PG_PASSWORD = ''
    PG_DATABASE = 'em2'

    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_DATABASE = 0

    LOCAL_DOMAIN = 'no-domain-set'

    def __init__(self, **custom_settings):
        for name, value in custom_settings.items():
            if not hasattr(self, name):
                raise ConfigException('{} is not a valid setting name'.format(name))
            setattr(self, name, value)
