from setuptools import setup
from em2 import VERSION

description = """
em2
===
"""

setup(
    name='em2_core',
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
    ]
)
