from importlib import import_module

from arq import RedisSettings


def import_string(dotted_path):
    """
    Stolen from django. Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError as e:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from e

    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError('Module "%s" does not define a "%s" attribute' % (module_path, class_name)) from e


class Settings:
    COMMS_HEAD_REQUEST_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY = (-10, 1)
    COMMS_PUSH_TOKEN_EARLY_EXPIRY = 10
    COMMS_DNS_CACHE_EXPIRY = 7200
    COMMS_HTTP_TIMEOUT = 4

    DATASTORE_CLS = 'em2.ds.NullDataStore'
    PUSHER_CLS = 'em2.comms.NullPusher'
    FALLBACK_CLS = 'em2.comms.fallback.FallbackHandler'

    PG_HOST = 'localhost'
    PG_PORT = '5432'
    PG_USER = 'postgres'
    PG_PASSWORD = ''
    PG_DATABASE = 'em2'

    PG_POOL_MINSIZE = 1
    PG_POOL_MAXSIZE = 10
    PG_POOL_TIMEOUT = 60.0

    LOCAL_DOMAIN = 'no-domain-set'
    PRIVATE_DOMAIN_KEY = 'no-key-set'

    TIMEZONE = 'utc'

    FALLBACK_USERNAME = None
    FALLBACK_PASSWORD = None
    FALLBACK_ENDPOINT = None

    def __init__(self, **custom_settings):
        """
        :param custom_settings: Custom settings to override defaults, only attributes already defined
            can be set.
        """
        redis_kwargs = 'R_HOST', 'R_PORT', 'R_DATABASE', 'R_PASSWORD'
        redis_settings = {}
        for kw in redis_kwargs:
            v = custom_settings.pop(kw, None)
            if v is not None:
                redis_settings[kw.replace('R_', '').lower()] = v
        self.redis = RedisSettings(**redis_settings)

        for name, value in custom_settings.items():
            if not hasattr(self, name):
                raise TypeError('{} is not a valid setting name'.format(name))
            setattr(self, name, value)

    @property
    def datastore_cls(self):
        return import_string(self.DATASTORE_CLS)

    @property
    def pusher_cls(self):
        return import_string(self.PUSHER_CLS)

    @property
    def fallback_cls(self):
        return import_string(self.FALLBACK_CLS)
