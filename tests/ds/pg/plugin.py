import os

import pytest
import psycopg2
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session

from em2.ds.pg.datastore import PostgresDataStore, ConnectionContextManager
from em2.ds.pg.models import Base

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

    engine = sa_create_engine(dsn)
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()
    cur.execute('DROP DATABASE {}'.format(DATABASE['database']))
    cur.close()
    conn.close()


@pytest.yield_fixture
def Session(db):
    connection = db.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(bind=db)
    _Session = scoped_session(session_factory)
    yield _Session

    transaction.rollback()
    connection.close()
    _Session.remove()


@pytest.yield_fixture
def empty_db(Session):
    yield

    session = Session()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


class TestPostgresDataStore(PostgresDataStore):
    _conn_ctx = None

    def connection(self):
        # force the same connection to be used each time
        self._conn_ctx = self._conn_ctx or TestCtx(self.engine)
        return self._conn_ctx

    async def terminate(self):
        if self._conn_ctx is not None:
            await self._conn_ctx.terminate()


class TestCtx(ConnectionContextManager):
    conn = None

    async def __aenter__(self):
        if self.conn is None:
            self.conn = await self._engine._acquire()
            self.tr = await self.conn._begin()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def terminate(self):
        await self.tr.rollback()
        self.tr = None
        self._engine.release(self.conn)
        self.conn = None
