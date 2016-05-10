from setuptools import setup
from em2 import VERSION

description = """
em2
===
"""

pg_extra = [
    'SQLAlchemy>=1.0.12',
    'aiopg>=0.9.2',
    'psycopg2>=2.6.1',
]

http_extras = [
    'aiohttp>=0.21.5',
    'cchardet>=1.0.0',
]

redis_extras = [
    'aioredis>=0.2.6'
]

setup(
    name='em2',
    version=str(VERSION),
    description='em2',
    long_description=description,
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='email,em2',
    author='Samuel Colvin',
    author_email='s@muelcolvin.com',
    url='https://github.com/em-2/em2-core',
    license='MIT',
    packages=['em2'],
    zip_safe=True,
    install_requires=[
        'pytz>=2015.7',
        'Cerberus>=0.9.2',
        'aiodns>=1.0.1',
    ],
    extras_require={
        'postgres': pg_extra,
        'http': http_extras,
        'redis': redis_extras,
        'all': pg_extra + http_extras + redis_extras,
    }
)
