import asyncio
import logging

import asyncpg
from async_timeout import timeout

from em2.settings import Settings

logger = logging.getLogger('em2.database')


async def lenient_pg_connection(settings, _retry=0):
    no_db_dsn, _ = settings.pg_dsn.rsplit('/', 1)

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
    log = logger.info if _retry > 0 else logger.debug
    log('pg connection successful, version: %s', await conn.fetchval('SELECT version()'))
    return conn


async def prepare_database(settings: Settings, overwrite_existing: bool) -> bool:
    """
    (Re)create a fresh database and run migrations.

    :param overwrite_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database has been (re)created
    """
    conn = await lenient_pg_connection(settings)
    try:
        if not overwrite_existing:
            # this check is technically unnecessary but avoids an ugly postgres error log
            exists = await conn.fetchval('SELECT 1 AS result FROM pg_database WHERE datname=$1', settings.pg_name)
            if exists:
                logger.info('database already exists ✓')
                return False

        logger.debug('attempting to create database "%s"...', settings.pg_name)
        try:
            await conn.execute('CREATE DATABASE {}'.format(settings.pg_name))
        except (asyncpg.DuplicateDatabaseError, asyncpg.UniqueViolationError):
            if not overwrite_existing:
                logger.info('database already exists, skipping creation')
                return False
            else:
                logger.debug('database already exists...')
        else:
            logger.debug('database did not exist, now created')

        logger.debug('settings db timezone to utc...')
        await conn.execute(f"ALTER DATABASE {settings.pg_name} SET TIMEZONE TO 'UTC';")
    finally:
        await conn.close()

    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        logger.debug('creating tables from model definition...')
        async with conn.transaction():
            await conn.execute(settings.models_sql)
    finally:
        await conn.close()
    logger.info('database successfully setup ✓')
    return True
