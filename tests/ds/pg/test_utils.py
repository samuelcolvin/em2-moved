import asyncio

from em2 import Settings
from em2.utils import info


class PseudoLogger:
    def __init__(self):
        self.log = ''

    def info(self, *args):
        self.log += 'info | {}\n'.format(' '.join(args))

    def warning(self, *args):
        self.log += 'warn | {}\n'.format(' '.join(args))


def test_info(loop, empty_db):
    asyncio.set_event_loop(loop)
    s = Settings(PG_DATABASE='em2_test')
    l = PseudoLogger()
    info(s, l)
    assert 'info | em2' in l.log
    assert 'info | pg db:    em2_test' in l.log
    assert 'info | total 0 conversations' in l.log
