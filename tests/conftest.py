import os
import pytest

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session
from em2pg.models import Base

pytest_plugins = 'em2_tests.plugins.asyncio'


DATABASE = {
    'drivername': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'username': 'postgres',
    'password': os.getenv('PG_PASS', ''),
    'database': 'em2_test'
}


@pytest.fixture(scope='session')
def dsn():
    return str(URL(**DATABASE))


@pytest.yield_fixture(scope='session')
def db(dsn):
    conn = psycopg2.connect(user=DATABASE['username'], password=DATABASE['password'],
                            host=DATABASE['host'], port=DATABASE['port'])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(DATABASE['database']))
    cur.execute('CREATE DATABASE {}'.format(DATABASE['database']))

    engine = create_engine(dsn)
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()
    cur.execute('DROP DATABASE {}'.format(DATABASE['database']))
    cur.close()
    conn.close()


@pytest.yield_fixture()
def Session(db):
    connection = db.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(bind=db)
    _Session = scoped_session(session_factory)
    yield _Session

    transaction.rollback()
    connection.close()
    _Session.remove()
