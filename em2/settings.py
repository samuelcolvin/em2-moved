from enum import Enum
from pathlib import Path

from arq import RedisSettings
from pydantic import BaseSettings, PyObject
from pydantic.utils import make_dsn


class Mode(str, Enum):
    main = 'main'
    auth = 'auth'


class Settings(BaseSettings):
    DEBUG = False
    LOG_TIMES = True
    COMMIT: str = None

    COMMS_DOMAIN_CACHE_TIMEOUT = 86_400
    COMMS_PLATFORM_TOKEN_TIMEOUT = 86_400
    COMMS_PLATFORM_TOKEN_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY: list = (-10_000, 2_000)
    COMMS_PUSH_TOKEN_EARLY_EXPIRY = 10
    COMMS_DNS_CACHE_EXPIRY = 7200
    COMMS_HTTP_TIMEOUT = 4
    # only ever change these during testing!!!
    COMMS_PROTO = 'https'
    COMMS_VERIFY_SSL = True

    COMMS_DNS_IPS = ['8.8.8.8', '8.8.4.4']

    auth_token_validity = 7 * 86_400
    auth_bcrypt_work_factor = 13
    auth_token_key = b'you need to replace me with a real Fernet keyxxxxxxx='

    pusher_cls: PyObject = 'em2.push.Pusher'
    fallback_cls: PyObject = 'em2.fallback.FallbackHandler'
    db_cls: PyObject = 'em2.core.Database'
    authenticator_cls: PyObject = 'em2.foreign.auth.Authenticator'

    WEB_PORT = 8000

    pg_host = 'localhost'
    pg_port = '5432'
    pg_user = 'postgres'
    pg_password = ''
    pg_main_name = 'em2'
    pg_auth_name = 'em2_auth'

    mode = Mode.main

    pg_pool_minsize = 1
    pg_pool_maxsize = 10

    # the domain at which other platforms connect to this node, eg. the "foreign" app's endpoint
    EXTERNAL_DOMAIN = 'em2-domain-set'
    PRIVATE_DOMAIN_KEY_FILE = 'no-key-file-set'

    FALLBACK_USERNAME: str = None
    FALLBACK_PASSWORD: str = None
    FALLBACK_ENDPOINT: str = None

    R_HOST = 'localhost'
    R_PORT = 6379
    R_DATABASE = 0
    R_PASSWORD: str = None

    COOKIE_NAME = 'em2session'
    SECRET_SESSION_KEY = b'you need to replace me with a real Fernet keyxxxxxxx='
    THIS_DIR = Path(__file__).resolve().parent
    FRONTEND_RECIPIENTS_BASE = 'frontend:recipients:{}'
    FRONTEND_JOBS_BASE = 'frontend:jobs:{}'

    class Config:
        env_prefix = 'EM2_'
        ignore_extra = False

    @property
    def private_domain_key(self):
        return Path(self.PRIVATE_DOMAIN_KEY_FILE).read_text()

    @property
    def pg_name(self):
        return self.pg_main_name if self.mode == Mode.main else self.pg_auth_name

    @property
    def pg_dsn(self):
        kwargs = {f: getattr(self, f'pg_{f}') for f in ('name', 'password', 'host', 'port', 'user')}
        return make_dsn(driver='postgres', **kwargs)

    @property
    def models_sql(self):
        f = 'main_models.sql' if self.mode == Mode.main else 'auth_models.sql'
        return (self.THIS_DIR / 'extras' / f).read_text()

    @property
    def redis(self):
        return RedisSettings(
            host=self.R_HOST,
            port=self.R_PORT,
            database=self.R_DATABASE,
            password=self.R_PASSWORD,
        )
