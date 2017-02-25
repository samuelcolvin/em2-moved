from importlib.machinery import SourceFileLoader
from pathlib import Path
from setuptools import find_packages, setup

description = """
em2
===
"""

# avoid loading the package before requirements are installed:
version = SourceFileLoader('version', 'em2/version.py').load_module()
requirements = [r for r in Path('em2/requirements.txt').read_text().split('\n') if r and not r.startswith('#')]

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
    packages=find_packages(include=('em2*',)),
    zip_safe=True,
    package_data={
        'em2': ['requirements.txt'],
    },
    install_requires=requirements,
)
