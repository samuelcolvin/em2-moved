#!/usr/bin/env python3.6
import asyncio
import os

from em2 import Settings
from em2.logging import logger, setup_logging
from em2.utils import wait_for_services

commands = []


def command(func):
    commands.append(func)
    return func


@command
def web_run(settings):
    from gunicorn.app.base import BaseApplication
    from em2.comms.http import create_app
    from em2.ds.pg.utils import prepare_database

    wait_for_services(settings)
    prepare_database(settings, delete_existing=False)

    config = dict(
        worker_class='aiohttp.worker.GunicornWebWorker',
        bind=f'0.0.0.0:{settings.WEB_PORT}',
        max_requests=5000,
        max_requests_jitter=500,
    )

    class Application(BaseApplication):
        def load_config(self):
            for k, v in config.items():
                self.cfg.set(k, v)

        def load(self):
            return create_app(settings)

    Application().run()


@command
def web_check(settings):
    from em2.utils import check_server
    loop = asyncio.get_event_loop()
    failed = loop.run_until_complete(check_server(settings))
    failed and exit(1)


def worker_check(settings):
    from em2.worker import Worker
    exit(Worker.check_health(settings=settings))


@command
def worker_run(settings):
    from pathlib import Path
    from arq import RunWorkerProcess
    from em2.ds.pg.utils import check_database_exists

    wait_for_services(settings)
    check_database_exists(settings)

    # TODO allow arq to import modules
    worker = Path(__file__).parent.joinpath('worker.py')
    RunWorkerProcess(str(worker), 'Worker')


@command
def info(settings):
    from em2.utils import info as info_
    logger.log(info_(settings))


def main():
    setup_logging()
    settings = Settings()

    command_lookup = {c.__name__: c for c in commands}

    command_ = os.getenv('EM2_COMMAND', 'info')

    func = command_lookup[command_]
    logger.info('running %s...', func.__name__)
    func(settings)


if __name__ == '__main__':
    main()
