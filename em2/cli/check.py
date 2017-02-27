#!/usr/bin/env python3.6
import asyncio
import os

from em2 import Settings
from em2.exceptions import ConfigException
from em2.logging import logger, setup_logging

command_list = []


def command(func):
    command_list.append(func)
    return func


@command
def web_check(settings):
    from em2.utils import check_server
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_server(settings)) and exit(1)


@command
def worker_check(settings):
    from em2.worker import Worker
    Worker.check_health(settings=settings) and exit(1)


def cli(command_):
    setup_logging()
    settings = Settings()

    command_lookup = {c.__name__: c for c in command_list}

    func = command_lookup.get(command_)
    if func is None:
        options = ', '.join(sorted(command_lookup.keys()))
        raise ConfigException(f'invalid command "{command_}", options are: {options}')
    logger.info('running %s...', func.__name__)
    func(settings)


def main():
    command_ = os.getenv('COMMAND', 'web')
    # make sure web_check runs here when EM2_COMMAND is "web", also worker_check instead of "worker"
    command_ += '_check'
    cli(command_)


if __name__ == '__main__':
    main()
