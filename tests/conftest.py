import os
import datetime
import pytest
import asyncio
import gc

import psycopg2
import factory
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session
from em2pg.models import Base, Conversation


DATABASE = {
    'drivername': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'username': 'postgres',
    'password': os.getenv('PG_PASS', ''),
    'database': 'em2_test'
}


@pytest.fixture(scope='session')
def db():
    conn = psycopg2.connect(user=DATABASE['username'], password=DATABASE['password'],
                            host=DATABASE['host'], port=DATABASE['port'])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(DATABASE['database']))
    cur.execute('CREATE DATABASE {}'.format(DATABASE['database']))
    cur.close()
    conn.close()

    engine = create_engine(URL(**DATABASE))

    Base.metadata.create_all(engine)
    return engine


@pytest.yield_fixture(scope='function')
def Session(db):
    connection = db.engine.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(bind=db)
    _Session = scoped_session(session_factory)
    yield _Session

    transaction.rollback()
    connection.close()
    _Session.remove()


@pytest.fixture
def conversation_factory(Session):
    class ConversationFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = Conversation
            sqlalchemy_session = Session

        global_id = factory.Sequence(lambda n: 'con_{}'.format(n))
        creator = factory.Sequence(lambda n: 'user{}@example.com'.format(n))
        subject = factory.Sequence(lambda n: 'conversation {}'.format(n))
        timestamp = factory.Sequence(lambda n: datetime.datetime.now())
        status = 'draft'

    return ConversationFactory


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):
    """
    Run coroutines in an event loop instead of a normal function call.
    """
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        loop = asyncio.get_event_loop()
        funcargs = pyfuncitem.funcargs
        testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        loop.run_until_complete(asyncio.ensure_future(pyfuncitem.obj(**testargs)))
        return True


@pytest.yield_fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)

    yield loop

    loop.stop()
    loop.run_forever()
    loop.close()
    gc.collect()
    asyncio.set_event_loop(None)
