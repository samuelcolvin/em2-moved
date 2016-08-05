from importlib.machinery import SourceFileLoader
from setuptools import setup

description = """
em2
===
"""

pg_extra = [
    'SQLAlchemy>=1.0.12',
    'aiopg>=0.9.2',
    'psycopg2>=2.6.2',
]

http_extras = [
    'aiohttp>=0.22.4',
    'cchardet>=1.0.0',
]

redis_extras = [
    'aioredis>=0.2.6',
    'arq>=0.0.4',
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
    url='https://github.com/em-2/em2-core',
    license='MIT',
    packages=['em2'],
    zip_safe=True,
    install_requires=[
        'pytz>=2016.4',
        'Cerberus>=0.9.2',
        'aiodns>=1.0.1',
        'pycrypto==2.6.1',
    ],
    extras_require={
        'postgres': pg_extra,
        'http': http_extras,
        'redis': redis_extras,
        'all': pg_extra + http_extras + redis_extras,
    }
)
