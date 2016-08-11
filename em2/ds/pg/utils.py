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


def prepare_database(settings: Settings, skip_existing=False):
    conn = psycopg2.connect(**pg_connect_kwargs(settings))
    conn.autocommit = True
    cur = conn.cursor()
    if skip_existing:
        args = settings.PG_DATABASE,
        cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', args)
        if cur.fetchone()[0]:
            return True
    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))
    cur.execute('CREATE DATABASE {}'.format(settings.PG_DATABASE))
    cur.close()
    conn.close()

    engine = create_engine(get_dsn(settings))
    Base.metadata.create_all(engine)
    engine.dispose()
    if skip_existing:
        return False
