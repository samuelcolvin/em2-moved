import logging
import logging.config
import os

logger = logging.getLogger('em2.main')


def prepare_log_config(settings) -> dict:
    dft_log_level = 'DEBUG' if settings.DEBUG else 'INFO'
    v = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'em2.default': {
                'format': '%(name)17s %(asctime)s| %(message)s' if settings.LOG_TIMES else '%(name)17s: %(message)s',
                'datefmt': '%H:%M:%S',
            },
        },
        'handlers': {
            'em2.default': {
                'level': dft_log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'em2.default'
            },
            'sentry': {
                'level': 'WARNING',
                'class': 'raven.handlers.logging.SentryHandler',
                'dsn': os.getenv('RAVEN_DSN', None),
                'release': settings.COMMIT,
                'name': os.getenv('SERVER_NAME', '-')
            },
        },
        'loggers': {
            'em2': {
                'handlers': ['em2.default', 'sentry'],
                'level': dft_log_level,
                'propagate': False,
            },
            'arq': {
                'handlers': ['em2.default', 'sentry'],
                'level': 'INFO',
                'propagate': False,
            },
            'aiohttp': {
                'handlers': ['em2.default', 'sentry'],
                'level': 'WARNING',
            },
        },
    }
    return v


def setup_logging(settings, *, log_config: dict=None):
    if log_config is None:
        log_config = prepare_log_config(settings)
    logging.config.dictConfig(log_config)
