from setuptools import setup
from em2_tests import VERSION

setup(
    name='em2_tests',
    version=str(VERSION),
    description='em2 test utilities',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='em2',
    author='Samuel Colvin',
    author_email='s@muelcolvin.com',
    url='https://github.com/em-2/em2-test-utils',
    license='MIT',
    packages=['em2_tests'],
    zip_safe=True,
    install_requires=[
        'codecov>=1.6.3',
        'coverage>=4.1b1',
        'flake8>=2.5.1',
        'pep8>=1.7.0',
        'pytest>=2.8.5',
        'pytest-cov>=2.2.0',
    ]
)
