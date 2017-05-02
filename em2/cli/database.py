import asyncpg

from em2.settings import Settings
from em2.utils.dsn import make_dsn

DB_EXISTS = 'SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=$1)'


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
                print('database "{}" already exists, skipping'.format(settings.PG_NAME))
                return False
            else:
                print('database "{}" already exists...'.format(settings.PG_NAME))
        else:
            print('database "{}" does not yet exist'.format(settings.PG_NAME))
            print('creating database "{}"...'.format(settings.PG_NAME))
            await conn.execute('CREATE DATABASE {}'.format(settings.PG_NAME))
    finally:
        await conn.close()

    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        print('creating tables from model definition...')
        await conn.execute(settings.models_sql)
    finally:
        await conn.close()
    return True
