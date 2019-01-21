#!/usr/bin/env python3.7
import asyncio
import logging
import os

import uvloop

from atoolbox.logs import setup_logging
from em2 import Settings
from em2.exceptions import ConfigException

command_lookup = {}
logger = logging.getLogger('em2.main')


def command(func):
    command_lookup[func.__name__] = func
    return func


@command
def web_check(settings):
    from em2.utils.network import check_server
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_server(settings, '/d/')) and exit(1)


@command
def auth_check(settings):
    from em2.utils.network import check_server
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_server(settings)) and exit(1)


@command
def worker_check(settings):
    from em2.worker import Worker
    Worker.check_health(settings=settings) and exit(1)


def execute(command_):
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    settings = Settings()
    logging_client = setup_logging(debug=settings.DEBUG, main_logger_name='em2')
    try:
        func = command_lookup.get(command_)
        if func is None:
            options = ', '.join(sorted(command_lookup.keys()))
            raise ConfigException(f'invalid command "{command_}", options are: {options}')
        logger.info('running %s...', func.__name__)
        func(settings)
    finally:
        loop = asyncio.get_event_loop()
        if logging_client and not loop.is_closed():
            transport = logging_client.remote.get_transport()
            transport and loop.run_until_complete(transport.close())


def main():
    command_ = os.getenv('EM2_COMMAND', 'web')
    # make sure web_check runs here when EM2_COMMAND is "web", also worker_check instead of "worker"
    command_ += '_check'
    execute(command_)


if __name__ == '__main__':
    main()
