import os
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
    ENV_PREFIX = 'EM2_'

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
    AUTHENTICATOR_CLS = 'em2.comms.auth.RedisDNSAuthenticator'

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

    R_HOST = 'localhost'
    R_PORT = 6379
    R_DATABASE = 0
    R_PASSWORD = None

    def __init__(self, **custom_settings):
        """
        :param custom_settings: Custom settings to override defaults, only attributes already defined can be set.
        """
        for name, value in custom_settings.items():
            if not hasattr(self, name):
                raise TypeError('{} is not a valid setting name'.format(name))
            setattr(self, name, value)
        self.substitute_environ()

        self.redis = RedisSettings(
            host=self.R_HOST,
            port=self.R_PORT,
            database=self.R_DATABASE,
            password=self.R_PASSWORD,
        )

    def substitute_environ(self):
        """
        Substitute environment variables into settings.
        """
        for attr_name in dir(self):
            if attr_name == 'ENV_PREFIX' or attr_name.startswith('_') or attr_name.upper() != attr_name:
                continue

            orig_value = getattr(self, attr_name)
            env_var = os.getenv(self.ENV_PREFIX + attr_name, None)
            if env_var:
                if isinstance(orig_value, int):
                    env_var = int(env_var)
                elif isinstance(orig_value, bytes):
                    env_var = env_var.encode()
                # could do floats here and lists etc via json
                setattr(self, attr_name, env_var)

    @property
    def datastore_cls(self):
        return import_string(self.DATASTORE_CLS)

    @property
    def pusher_cls(self):
        return import_string(self.PUSHER_CLS)

    @property
    def fallback_cls(self):
        return import_string(self.FALLBACK_CLS)

    @property
    def authenticator_cls(self):
        return import_string(self.AUTHENTICATOR_CLS)
