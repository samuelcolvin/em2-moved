from app import dsn, DATABASE

import psycopg2
from sqlalchemy import create_engine

from em2.ds.pg.models import Base


conn = psycopg2.connect(user=DATABASE['username'], password=DATABASE['password'],
                        host=DATABASE['host'], port=DATABASE['port'])
conn.autocommit = True
cur = conn.cursor()
cur.execute('DROP DATABASE IF EXISTS {}'.format(DATABASE['database']))
cur.execute('CREATE DATABASE {}'.format(DATABASE['database']))

engine = create_engine(dsn)
Base.metadata.create_all(engine)
