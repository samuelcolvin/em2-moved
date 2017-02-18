from contextlib import contextmanager
from time import sleep

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from em2 import Settings
from em2.logging import logger

from .models import Base


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


def prepare_database(settings: Settings, *, delete_existing: bool, print_func=print) -> bool:  # pragma: no cover
    """
    (Re)create a fresh database and run migrations.

    :param settings: settings to use
    :param delete_existing: whether or not to drop an existing database if it exists
    :param print_func: function to use for printing, eg. could be set to `logger.info`
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
                print_func('database "{}" already exists, not recreating it'.format(db_name))
                return False
            else:
                print_func('dropping existing connections to "{}"...'.format(db_name))
                cur.execute(DROP_CONNECTIONS, (db_name,))
                print_func('dropping database "{}" as it already exists...'.format(db_name))
                cur.execute('DROP DATABASE {}'.format(db_name))
        else:
            print_func('database "{}" does not yet exist'.format(db_name))

        print_func('creating database "{}"...'.format(db_name))
        cur.execute('CREATE DATABASE {}'.format(db_name))

    engine = create_engine(get_dsn(settings))
    print_func('creating tables from model definition...')
    Base.metadata.create_all(engine)
    engine.dispose()
    print_func('db and tables creation finished.')
    return True
