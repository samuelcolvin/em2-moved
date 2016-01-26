#!/usr/bin/env python
"""
Install requirements from both *_requirements.txt and the install_requires section of setup.py
"""
import os
import re
from tempfile import NamedTemporaryFile
import pip

THIS_DIR = os.path.dirname(__file__)


def get_setup_requirements(setup_path):
    with open(os.path.join(THIS_DIR, setup_path)) as f:
        text = f.read()

    m = re.search('install_requires=\[(.*?)\]', text, re.S)
    assert m

    return re.findall("'(.*?)'", m.groups()[0])


def get_txt_requirements(fn):
    with open(os.path.join(THIS_DIR, fn)) as f:
        return list(filter(bool, f.read().split('\n')))

if __name__ == '__main__':
    test_req = get_txt_requirements('test_requirements.txt')
    pg_req = get_txt_requirements('pg_requirements.txt')
    setup_req = get_setup_requirements('../setup.py')
    packages = sorted(test_req + pg_req + setup_req)
    reqs = '\n'.join(packages)
    print('Installing all requirements:\n{}\n'.format(reqs))
    with NamedTemporaryFile() as tmp:
        tmp.write(reqs.encode('utf8'))
        tmp.flush()
        pip.main(['install', '-r', tmp.name])
