import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from aiopg.sa.engine import _create_engine

from .models import Base
from .datastore import PostgresDataStore


DEFAULT_DATABASE = {
    'drivername': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'username': 'postgres',
    'password': '',
    'database': 'em2_test',
}


def prepare_database(database: dict=DEFAULT_DATABASE, skip_existing=False):
    conn = psycopg2.connect(user=database['username'], password=database['password'],
                            host=database['host'], port=database['port'])
    conn.autocommit = True
    cur = conn.cursor()
    if skip_existing:
        args = database['database'],
        cur.execute('SELECT EXISTS (SELECT datname FROM pg_catalog.pg_database WHERE datname=%s)', args)
        if cur.fetchone()[0]:
            return True
    cur.execute('DROP DATABASE IF EXISTS {database}'.format(**database))
    cur.execute('CREATE DATABASE {database}'.format(**database))

    engine = create_engine(dict_to_dsn(database))
    Base.metadata.create_all(engine)
    if skip_existing:
        return False


def dict_to_dsn(d):
    return str(URL(**d))


def create_datastore(loop, database: dict=DEFAULT_DATABASE):
    engine = loop.run_until_complete(_create_engine(dict_to_dsn(database), loop=loop))
    return PostgresDataStore(engine)
