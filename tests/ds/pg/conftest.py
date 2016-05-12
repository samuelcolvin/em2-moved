import pytest
import psycopg2

from em2 import Settings
from em2.ds.pg.utils import pg_connect_kwargs

pytest_plugins = 'tests.ds.pg.plugin'


@pytest.yield_fixture
def pg_conn():
    settings = Settings(PG_DATABASE='test_prepare_database')
    conn = psycopg2.connect(**pg_connect_kwargs(settings))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))

    yield settings, cur

    cur.execute('DROP DATABASE IF EXISTS {}'.format(settings.PG_DATABASE))
    cur.close()
    conn.close()
