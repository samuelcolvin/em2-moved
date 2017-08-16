import asyncio
import logging

import asyncpg
from async_timeout import timeout
from pydantic.utils import make_dsn

from em2.settings import Settings

logger = logging.getLogger('em2.database')


async def lenient_pg_connection(settings, _retry=0):
    no_db_dsn = make_dsn(**{
        **settings.pg_dsn_kwargs,
        **{'name': None}
    })

    try:
        with timeout(2):
            conn = await asyncpg.connect(dsn=no_db_dsn)
    except asyncpg.CannotConnectNowError as e:
        if _retry < 5:
            logger.warning('pg temporary connection error %s, %d retries remaining...', e, 5 - _retry)
            await asyncio.sleep(2)
            return await lenient_pg_connection(settings, _retry=_retry + 1)
        else:
            raise
    logger.info('pg connection successful, version: %s', await conn.fetchval('SELECT version()'))
    return conn


async def prepare_database(settings: Settings, overwrite_existing: bool) -> bool:
    """
    (Re)create a fresh database and run migrations.

    :param overwrite_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database has been (re)created
    """
    conn = await lenient_pg_connection(settings)
    try:
        logger.info('attempting to create database "%s"...', settings.PG_NAME)
        try:
            await conn.execute('CREATE DATABASE {}'.format(settings.PG_NAME))
        except (asyncpg.DuplicateDatabaseError, asyncpg.UniqueViolationError):
            if not overwrite_existing:
                logger.info('database already exists, skipping')
                return False
            else:
                logger.info('database already exists...')
        else:
            logger.info('database did not exist, now created')

        logging.info('settings db timezone to utc...')
        await conn.execute("ALTER DATABASE {} SET TIMEZONE TO 'UTC';".format(settings.PG_NAME))
    finally:
        await conn.close()

    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        logger.info('creating tables from model definition...')
        await conn.execute(settings.models_sql)
    finally:
        await conn.close()
    return True
