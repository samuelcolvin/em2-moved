import os

DATABASE = {
    'drivername': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'username': 'postgres',
    'password': os.getenv('PG_PASS', ''),
    'database': 'em2'
}
