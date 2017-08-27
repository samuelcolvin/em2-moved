#!/usr/bin/env python3.6
import asyncio
import os
import sys
from time import sleep

from arq import create_pool_lenient

from em2 import VERSION, Settings
from em2.logging import logger
from em2.run.check import command, execute
from em2.utils.database import prepare_database as _prepare_database
from em2.utils.network import wait_for_services

# imports are local where possible so commands (especially check) are as fast to run as possible


@command
def web(settings: Settings):
    import uvloop
    from aiohttp.web import run_app
    from em2 import create_app
    # logger.info(settings.to_string(True))

    asyncio.get_event_loop().close()
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()

    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    logger.info('starting server...')
    app = create_app(settings)
    try:
        run_app(app, port=settings.web_port, loop=loop, print=lambda v: None, access_log=None, shutdown_timeout=5)
    finally:
        logger.info('server shutdown')
        sleep(0.01)  # time for the log message to propagate


@command
def reset_database(settings: Settings):
    if not (os.getenv('CONFIRM_DATABASE_RESET') == 'confirm' or input('Confirm database reset? [yN] ') == 'y'):
        logger.warning('cancelling')
    else:
        logger.info('resetting database...')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_prepare_database(settings, True))
        logger.info('done.')


async def _flush_redis(settings: Settings, loop):
    pool = await create_pool_lenient(settings.redis, loop=loop)
    async with pool.get() as redis:
        await redis.flushdb()


@command
def flush_redis(settings: Settings):
    if not (os.getenv('CONFIRM_REDIS_FLUSH') == 'confirm' or input('Confirm redis flush? [yN] ') == 'y'):
        logger.warning('cancelling')
    else:
        logger.info('flushing redis...')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_flush_redis(settings, loop))
        logger.info('done.')


@command
def worker(settings: Settings):
    from arq import RunWorkerProcess

    loop = asyncio.get_event_loop()
    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    RunWorkerProcess('em2.worker', 'Worker')


@command
def info(settings: Settings):
    import aiohttp
    import arq
    logger.info(f"""em2 info:
    Python:     {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}
    em2:        {VERSION}
    aiohttp:    {aiohttp.__version__}
    arq:        {arq.VERSION}
    domain:     {settings.EXTERNAL_DOMAIN}
    debug:      {settings.DEBUG}
    main pg db: {settings.pg_main_name}
    auth pg db: {settings.pg_auth_name}
    redis db:   {settings.R_DATABASE}""")


@command
def shell(settings: Settings):
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
    if command:
        print(f'using command line argument to set command EM2_COMMAND="{command}"', flush=True)
        os.environ['EM2_COMMAND'] = command

    command_ = os.getenv('EM2_COMMAND', 'info')
    execute(command_)


if __name__ == '__main__':
    main()
