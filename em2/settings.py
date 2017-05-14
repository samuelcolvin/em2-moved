from pathlib import Path

from arq import RedisSettings
from pydantic import BaseSettings, Module
from pydantic.utils import make_dsn


class Settings(BaseSettings):
    DEBUG = False
    COMMAND = 'info'

    COMMS_HEAD_REQUEST_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY: list = (-10, 1)
    COMMS_PUSH_TOKEN_EARLY_EXPIRY = 10
    COMMS_DNS_CACHE_EXPIRY = 7200
    COMMS_HTTP_TIMEOUT = 4
    # only ever change this during network testing!!!
    COMMS_SCHEMA = 'https'
    COMMS_DNS_IP: str = None

    # datastore_cls: Module = 'em2.ds.pg.PostgresDataStore'
    # pusher_cls: Module = 'em2.comms.web.push.WebDNSPusher'
    fallback_cls: Module = 'em2.fallback.FallbackHandler'
    db_cls: Module = 'em2.core.Database'
    authenticator_cls: Module = 'em2.foreign.auth.Authenticator'

    # default address for webservers eg. gunicorn to bind to
    WEB_PORT = 8000

    PG_HOST = 'localhost'
    PG_PORT = '5432'
    PG_USER = 'postgres'
    PG_PASSWORD = ''
    PG_NAME = 'em2'

    PG_POOL_MINSIZE = 1
    PG_POOL_MAXSIZE = 10

    LOCAL_DOMAIN = 'no-domain-set'
    PRIVATE_DOMAIN_KEY_FILE = 'no-key-file-set'

    TIMEZONE = 'utc'

    FALLBACK_USERNAME: str = None
    FALLBACK_PASSWORD: str = None
    FALLBACK_ENDPOINT: str = None

    R_HOST = 'localhost'
    R_PORT = 6379
    R_DATABASE = 0
    R_PASSWORD: str = None

    COOKIE_NAME = 'em2session'
    SECRET_KEY = b'i am not secure but 32 bits long'
    THIS_DIR = Path(__file__).resolve().parent

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis = RedisSettings(
            host=self.R_HOST,
            port=self.R_PORT,
            database=self.R_DATABASE,
            password=self.R_PASSWORD,
        )

    class Config:
        env_prefix = 'EM2_'
        ignore_extra = False

    @property
    def private_domain_key(self):
        return Path(self.PRIVATE_DOMAIN_KEY_FILE).read_text()

    @property
    def pg_dsn_kwargs(self):
        kwargs = {
            f: getattr(self, f'PG_{f.upper()}')
            for f in ('name', 'password', 'host', 'port', 'user')
        }
        kwargs['driver'] = 'postgres'
        return kwargs

    @property
    def pg_dsn(self):
        return make_dsn(**self.pg_dsn_kwargs)

    @property
    def models_sql(self):
        return (self.THIS_DIR / 'extras/models.sql').read_text()
