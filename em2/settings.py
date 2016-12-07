from arq import ConnectionSettings


class Settings(ConnectionSettings):
    COMMS_HEAD_REQUEST_TIMEOUT = 0.8
    COMMS_DOMAIN_CACHE_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_TIMEOUT = 86400
    COMMS_PLATFORM_TOKEN_LENGTH = 64
    COMMS_AUTHENTICATION_TS_LENIENCY = (-10, 1)
    COMMS_PUSH_TOKEN_EARLY_EXPIRY = 10
    COMMS_DNS_CACHE_EXPIRY = 7200
    COMMS_HTTP_TIMEOUT = 4

    DATASTORE_CLS = 'em2.ds.pg.datastore.PostgresDataStore'
    PUSHER_CLS = 'em2.comms.http.push.HttpDNSPusher'

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
