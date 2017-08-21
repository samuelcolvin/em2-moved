#!/usr/bin/env python3.6
import asyncio
import os
import sys
from time import sleep

from em2 import VERSION
from em2.logging import logger
from em2.run.check import command, execute
from em2.run.database import prepare_database as _prepare_database
from em2.utils.network import wait_for_services

# imports are local where possible so commands (especially check) are as fast to run as possible


@command
def web(settings):
    import uvloop
    from aiohttp.web import run_app
    from em2 import create_app
    # print(settings.to_string(True), flush=True)

    asyncio.get_event_loop().close()
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()

    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    logger.info('starting server...')
    app = create_app(settings)
    try:
        run_app(app, port=settings.WEB_PORT, loop=loop, print=lambda v: None, access_log=None, shutdown_timeout=5)
    finally:
        logger.info('server shutdown')
        sleep(0.01)  # time for the log message to propagate


@command
def reset_database(settings):
    if not (os.getenv('CONFIRM_DATABASE_RESET') == 'confirm' or input('Confirm database reset? [yN] ') == 'y'):
        logger.warning('cancelling')
    else:
        logger.info('resetting database...')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_prepare_database(settings, True))


@command
def worker(settings):
    from arq import RunWorkerProcess

    loop = asyncio.get_event_loop()
    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    RunWorkerProcess('em2.worker', 'Worker')


@command
def info(settings):
    import aiohttp
    import arq
    logger.info(f'em2')
    logger.info(f'Python:   {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    logger.info(f'em2:      {VERSION}')
    logger.info(f'aiohttp:  {aiohttp.__version__}')
    logger.info(f'arq:      {arq.VERSION}\n')
    logger.info(f'domain:   {settings.DOMESTIC_DOMAIN}')
    logger.info(f'command:  {settings.COMMAND}')
    logger.info(f'debug:    {settings.DEBUG}')
    logger.info(f'pg db:    {settings.PG_NAME}')
    logger.info(f'redis db: {settings.R_DATABASE}\n')


@command
def shell(settings):
    """
    Basic replica of django-extensions shell, ugly but very useful in development
    """
    EXEC_LINES = [
        'import asyncio, os, re, sys',
        'from datetime import datetime, timedelta, timezone',
        'from pathlib import Path',
        '',
        'from em2 import Settings',
        '',
        'loop = asyncio.get_event_loop()',
        'await_ = loop.run_until_complete',
        'settings = Settings()',
    ]
    EXEC_LINES += (
        ['print("\\n    Python {v.major}.{v.minor}.{v.micro}\\n".format(v=sys.version_info))'] +
        [f'print("    {l}")' for l in EXEC_LINES]
    )

    from IPython import start_ipython
    from IPython.terminal.ipapp import load_default_config
    c = load_default_config()

    c.TerminalIPythonApp.display_banner = False
    c.TerminalInteractiveShell.confirm_exit = False
    c.InteractiveShellApp.exec_lines = EXEC_LINES
    start_ipython(argv=(), config=c)


def main():
    # special cases where we use arguments so you don't have to mess with env variables.
    command = len(sys.argv) > 1 and sys.argv[1]
    if command in ('info', 'reset_database', 'shell'):
        print(f'using command line argument to set command EM2_COMMAND="{command}"', flush=True)
        os.environ['EM2_COMMAND'] = command

    command_ = os.getenv('EM2_COMMAND', 'info')
    execute(command_)


if __name__ == '__main__':
    main()
