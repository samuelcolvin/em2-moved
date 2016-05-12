import asyncio

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from aiopg.sa.engine import _create_engine

from em2 import Settings
from .models import Base
from .datastore import PostgresDataStore


def pg_connect_kwargs(settings: Settings):
    return dict(
        password=settings.PG_PASSWORD,
        host=settings.PG_HOST,
        port=settings.PG_PORT,
        user=settings.PG_USER
    )


def create_dsn(settings: Settings):
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
        cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', settings.PG_DATABASE)
        if cur.fetchone()[0]:
            return True
    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))
    cur.execute('CREATE DATABASE {}'.format(settings.PG_DATABASE))

    engine = create_engine(create_dsn(settings))
    Base.metadata.create_all(engine)
    return False


def create_datastore(settings: Settings, loop=None):
    loop = loop or asyncio.get_event_loop()
    engine = loop.run_until_complete(_create_engine(create_dsn(settings), loop=loop))
    return PostgresDataStore(engine)
