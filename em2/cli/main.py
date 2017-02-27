#!/usr/bin/env python3.6
import os

from em2.cli.check import cli, command
from em2.logging import logger
from em2.utils import wait_for_services


@command
def web(settings):
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
def worker(settings):
    from arq import RunWorkerProcess
    from em2.ds.pg.utils import check_database_exists

    wait_for_services(settings)
    check_database_exists(settings)

    RunWorkerProcess('em2.worker', 'Worker')


@command
def info(settings):
    from em2.utils import info as info_

    info_(settings, logger)


def main():
    command_ = os.getenv('COMMAND', 'info')
    cli(command_)


if __name__ == '__main__':
    main()
