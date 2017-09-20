#!/usr/bin/env python3.6
import asyncio
import os

from em2 import Settings
from em2.exceptions import ConfigException
from em2.logging import logger, setup_logging

command_lookup = {}


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
    settings = Settings()
    setup_logging(settings)

    func = command_lookup.get(command_)
    if func is None:
        options = ', '.join(sorted(command_lookup.keys()))
        raise ConfigException(f'invalid command "{command_}", options are: {options}')
    logger.info('running %s...', func.__name__)
    func(settings)


def main():
    command_ = os.getenv('EM2_COMMAND', 'web')
    # make sure web_check runs here when EM2_COMMAND is "web", also worker_check instead of "worker"
    command_ += '_check'
    execute(command_)


if __name__ == '__main__':
    main()
