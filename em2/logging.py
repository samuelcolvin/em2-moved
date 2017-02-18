import logging
import logging.config

logger = logging.getLogger('em2.main')


def prepare_log_config(log_level: str) -> dict:
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(name)10s %(asctime)s| %(message)s',
                'datefmt': '%H:%M:%S',
            },
        },
        'handlers': {
            'default': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'default'
            },
        },
        'loggers': {
            'em2': {
                'handlers': ['default'],
                'level': log_level,
            },
        },
    }


def setup_logging(*, log_config: dict=None, log_level='INFO'):
    if log_config is None:
        log_config = prepare_log_config(log_level)
    logging.config.dictConfig(log_config)
