import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from em2 import Settings

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


def prepare_database(settings: Settings, *, delete_existing: bool) -> bool:
    """
    (Re)create a fresh database and run migrations.

    :param settings: settings to use
    :param delete_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database has been (re)created
    """
    conn = psycopg2.connect(**pg_connect_kwargs(settings))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', (settings.PG_DATABASE,))
    already_exists = bool(cur.fetchone()[0])
    if already_exists:
        if not delete_existing:
            print('database "{s.PG_DATABASE}" already exists, skipping'.format(s=settings))
            return False
        else:
            print('dropping database "{s.PG_DATABASE}" as it already exists...'.format(s=settings))
            cur.execute('DROP DATABASE {s.PG_DATABASE}'.format(s=settings))
    else:
        print('database "{s.PG_DATABASE}" does not yet exist'.format(s=settings))

    print('creating database "{s.PG_DATABASE}"...'.format(s=settings))
    cur.execute('CREATE DATABASE {s.PG_DATABASE}'.format(s=settings))
    cur.close()
    conn.close()

    engine = create_engine(get_dsn(settings))
    print('creating tables from model definition...')
    Base.metadata.create_all(engine)
    engine.dispose()
    return True
