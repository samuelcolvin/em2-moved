import logging

import asyncpg
from pydantic.utils import make_dsn

from em2.settings import Settings

DB_EXISTS = 'SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=$1)'

logger = logging.getLogger('cli.database')


async def prepare_database(settings: Settings, overwrite_existing: bool) -> bool:
    """
    (Re)create a fresh database and run migrations.

    :param overwrite_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database has been (re)created
    """
    no_db_dsn = make_dsn(**{
        **settings.pg_dsn_kwargs,
        **{'name': None}
    })

    conn = await asyncpg.connect(dsn=no_db_dsn)
    try:
        db_exists = await conn.fetchval(DB_EXISTS, settings.PG_NAME)
        if db_exists:
            if not overwrite_existing:
                logger.info('database "%s" already exists, skipping', settings.PG_NAME)
                return False
            else:
                logger.info('database "%s" already exists...', settings.PG_NAME)
        else:
            logger.info('database "%s" does not yet exist', settings.PG_NAME)
            logger.info('creating database "%s"...', settings.PG_NAME)
            await conn.execute('CREATE DATABASE {}'.format(settings.PG_NAME))
    finally:
        await conn.close()

    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        logger.info('creating tables from model definition...')
        await conn.execute(settings.models_sql)
    finally:
        await conn.close()
    return True
