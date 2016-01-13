#!/usr/bin/env python
import os
import re
from tempfile import NamedTemporaryFile
import pip

THIS_DIR = os.path.dirname(__file__)


def get_setup_requirements():
    with open(os.path.join(THIS_DIR, 'setup.py')) as f:
        text = f.read()

    m = re.search('install_requires=\[(.*?)\]', text, re.S)
    assert m

    return re.findall("'(.*?)'", m.groups()[0])


if __name__ == '__main__':
    with open(os.path.join(THIS_DIR, 'dev_requirements.txt')) as f:
        dev_reqs = list(filter(bool, f.read().split('\n')))
    packages = dev_reqs + get_setup_requirements()
    packages.sort()
    reqs = '\n'.join(packages)
    print('Installing all requirements:\n{}\n'.format(reqs))
    with NamedTemporaryFile() as tmp:
        tmp.write(reqs.encode('utf8'))
        tmp.flush()
        pip.main(['install', '-r', tmp.name])
