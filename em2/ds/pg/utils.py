import logging
from contextlib import contextmanager
from time import sleep

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from em2 import Settings
from em2.exceptions import StartupException

from .models import Base

logger = logging.getLogger('em2.ds.pg.utils')


def pg_connect_kwargs(settings: Settings):
    return dict(
        password=settings.PG_PASSWORD,
        host=settings.PG_HOST,
        port=settings.PG_PORT,
        user=settings.PG_USER
    )


def get_dsn(settings: Settings):
    kwargs = pg_connect_kwargs(settings)
    kwargs.update(
        database=settings.PG_DATABASE,
        drivername='postgres',
        username=kwargs.pop('user'),
    )
    return str(URL(**kwargs))


def lenient_connection(retries=5, **db_settings):  # pragma: no cover
    try:
        return psycopg2.connect(
            password=db_settings['password'],
            host=db_settings['host'],
            port=db_settings['port'],
            user=db_settings['user'],
        )
    except psycopg2.Error as e:
        if retries <= 0:
            raise
        else:
            logger.warning('%s: %s (%d retries remaining)', e.__class__.__name__, e, retries)
            sleep(1)
            return lenient_connection(retries=retries - 1, **db_settings)


@contextmanager
def psycopg2_cursor(**db_settings):
    conn = lenient_connection(**db_settings)
    conn.autocommit = True
    cur = conn.cursor()

    yield cur

    cur.close()
    conn.close()


DROP_CONNECTIONS = """\
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = %s AND pid <> pg_backend_pid();
"""


def prepare_database(settings: Settings, *, delete_existing: bool) -> bool:  # pragma: no cover
    """
    (Re)create a fresh database and run migrations.

    :param settings: settings to use
    :param delete_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database as (re)created
    """
    db_name = settings.PG_DATABASE

    with psycopg2_cursor(**pg_connect_kwargs(settings)) as cur:
        cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', (db_name,))
        already_exists = bool(cur.fetchone()[0])
        if already_exists:
            if callable(delete_existing):
                _delete_existing = delete_existing()
            else:
                _delete_existing = bool(delete_existing)
            if not _delete_existing:
                logger.info('database "%s" already exists, not recreating it', db_name)
                return False
            else:
                logger.info('dropping existing connections to "%s"...', db_name)
                cur.execute(DROP_CONNECTIONS, (db_name,))
                logger.info('dropping database "%s" as it already exists...', db_name)
                cur.execute('DROP DATABASE {}'.format(db_name))
        else:
            logger.info('database "%s" does not yet exist', db_name)

        logger.info('creating database "%s"...', db_name)
        cur.execute('CREATE DATABASE {}'.format(db_name))

    engine = create_engine(get_dsn(settings))
    logger.info('creating tables from model definition...')
    Base.metadata.create_all(engine)
    engine.dispose()
    logger.info('db and tables creation finished.')
    return True


def check_database_exists(settings: Settings, retries=5):  # pragma: no cover
    db_name = settings.PG_DATABASE
    with psycopg2_cursor(**pg_connect_kwargs(settings)) as cur:
        cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', (db_name,))
        db_exists = bool(cur.fetchone()[0])
    if not db_exists:
        if retries <= 0:
            raise StartupException(f'database "{db_name}" does not exist')
        else:
            logger.warning('database "%s" does not exist (%d retries remaining)', db_name, retries)
            sleep(1)
            return check_database_exists(settings, retries - 1)
    logger.info('database "%s" does exist, connection ok', db_name)
