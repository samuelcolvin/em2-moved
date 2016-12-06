from importlib.machinery import SourceFileLoader
from setuptools import setup

description = """
em2
===
"""

pg_extra = [
    'SQLAlchemy>=1.1.3',
    'aiopg>=0.13.0',
    'psycopg2>=2.6.2',
]

http_extras = [
    'aiohttp>=1.1.6',
    'cchardet>=1.1.1',
]

redis_extras = [
    'aioredis>=0.2.9',
    'arq>=0.0.6',
]

# avoid loading the package before requirements are installed:
version = SourceFileLoader('version', 'em2/version.py').load_module()

setup(
    name='em2',
    version=str(version.VERSION),
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
    url='https://github.com/em-2/em2',
    license='MIT',
    packages=['em2'],
    zip_safe=True,
    install_requires=[
        'aiodns>=1.1.1',
        'Cerberus>=1.0.1',
        'msgpack-python>=0.4.8',
        'pycrypto==2.6.1',
        'pytz>=2016.10',
    ],
    extras_require={
        'postgres': pg_extra,
        'http': http_extras,
        'redis': redis_extras,
        'all': pg_extra + http_extras + redis_extras,
    }
)
