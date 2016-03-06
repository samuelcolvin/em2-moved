import os
import sys
import asyncio

from aiopg.sa.engine import _create_engine
from sqlalchemy.engine.url import URL

THIS_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(THIS_DIR, '../..'))

from em2.core import Controller  # noqa
from em2.comms.http import create_app  # noqa
from em2.ds.pg.datastore import PostgresDataStore  # noqa
from tests.fixture_classes import NullPropagator  # noqa

DATABASE = {
    'drivername': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'username': 'postgres',
    'password': os.getenv('PG_PASS', ''),
    'database': 'em2_test'
}

dsn = str(URL(**DATABASE))


loop = asyncio.get_event_loop()
engine = loop.run_until_complete(_create_engine(dsn, loop=loop))
ds = PostgresDataStore(engine)
ctrl = Controller(ds, NullPropagator())
app = create_app(ctrl, loop=loop)
