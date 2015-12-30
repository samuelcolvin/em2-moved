import datetime

import hashlib
from em2.base import Controller
from tests.py_datastore import SimpleDataStore


async def test_create_basic_conversation():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    await ctrl.conversations.create('text@example.com', 'foo bar')
    assert len(ds.data) == 1
    con = ds.data['0']
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    assert con['creator'] == 'text@example.com'
    assert con['status'] == 'draft'
    assert con['subject'] == 'foo bar'
    assert isinstance(con['timestamp'], datetime.datetime)
    hash_data = bytes('text@example.com_{}_foo bar'.format(con['timestamp'].isoformat()), 'utf8')
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert con['global_id'] == hash_result
