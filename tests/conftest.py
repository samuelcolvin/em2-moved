import pytest

import psycopg2
import factory
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session
from em2.models import Base
from em2 import settings
from em2.models import Conversation


DB_NAME = 'em2_test'


@pytest.fixture(scope='session')
def db():
    conn_settings = dict(settings.DATABASE)

    conn = psycopg2.connect(user=conn_settings['username'], password=conn_settings['password'],
                            host=conn_settings['host'], port=conn_settings['port'])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(DB_NAME))
    cur.execute('CREATE DATABASE {}'.format(DB_NAME))
    cur.close()
    conn.close()

    conn_settings['database'] = DB_NAME
    engine = create_engine(URL(**conn_settings))

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

    return ConversationFactory
