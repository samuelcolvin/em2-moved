import datetime
from copy import deepcopy

import pytest

from em2.base import Action, Verbs
from em2.common import Components
from em2.exceptions import BadDataException, BadHash

correct_data = {
    'creator': 'testing@example.com',
    'expiration': None,
    'messages': [
        {
            'author': 'testing@example.com',
            'body': 'the body',
            'id': 'd21625d617b1e8eb8989aa3d57a5aae691f9ed2a',
            'parent': None,
            'timestamp': datetime.datetime(2016, 1, 1),
        }
    ],
    'participants': [('testing@example.com', 'full'), ('receiver@remote.com', 'write')],
    'ref': 'the subject',
    'status': 'active',
    'subject': 'the subject',
    'timestamp': datetime.datetime(2016, 1, 2),
}
con_id = '0d35129317a6a6455609436c9aad1d11f2b0cb734d53b7222459d2452b25854f'

async def test_publish_simple_conversation(controller, timestamp):
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, timestamp=timestamp, remote=True)
    ds = controller.ds
    assert len(ds.data) == 0
    await controller.act(a, data=deepcopy(correct_data))

    assert len(ds.data) == 1
    assert ds.data[0]['con_id'] == con_id
    assert ds.data[0]['subject'] == 'the subject'
    assert len(ds.data[0]['messages']) == 1
    assert list(ds.data[0]['messages'].values())[0]['body'] == 'the body'
    assert ds.data[0]['timestamp'] == datetime.datetime(2016, 1, 2)
    assert len(ds.data[0]['participants']) == 2


async def test_publish_invalid_args(controller, timestamp):
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, timestamp=timestamp, remote=True)
    with pytest.raises(BadDataException) as excinfo:
        await controller.act(a, foo='bar')
    assert excinfo.value.args[0] == "Wrong kwargs for add, got: ['foo'], expected: ['data']"
    assert len(controller.ds.data) == 0

async def test_publish_no_timestamp(controller):
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, timestamp=None, remote=True)
    with pytest.raises(BadDataException) as excinfo:
        await controller.act(a, data=deepcopy(correct_data))
    assert excinfo.value.args[0] == 'remote actions should always have a timestamp'
    assert len(controller.ds.data) == 0


def modified_data(**kwargs):
    d2 = deepcopy(correct_data)
    d2.update(kwargs)
    return d2

bad_data = [
    (
        'missing_values',
        {'creator': 'testing@example.com'},
        '{"participants": "required field", "ref": "required field", "status": "required field", '
        '"subject": "required field", "timestamp": "required field"}',
    ),
    (
        'None',
        'None',
        'data must be a dict',
    ),
    (
        'string',
        'hello',
        'data must be a dict',
    ),
    (
        'extra_key',
        modified_data(foo='bar'),
        '{"foo": "unknown field"}',
    ),
    (
        'wrong_type',
        modified_data(creator=None),
        '{"creator": ["null value not allowed", "must be of string type"]}',
    ),
    (
        'bad_timestamp',
        modified_data(messages=[
            {
                'author': 'testing@example.com',
                'body': 'the body',
                'id': 'd21625d617b1e8eb8989aa3d57a5aae691f9ed2a',
                'parent': None,
                'timestamp': 123,
            }
        ]),
        '{"messages": {"0": {"timestamp": "must be of datetime type"}}}',
    ),
    (
        'list_extra_item',
        modified_data(participants=[('testing@example.com', 'full'), ('receiver@remote.com', 'write', 3)]),
        '{"participants": {"1": "max length is 2"}}',
    ),
    (
        'bad_first_parent',
        modified_data(messages=[
            {
                'author': 'testing@example.com',
                'body': 'the body',
                'id': 'd21625d617b1e8eb8989aa3d57a5aae691f9ed2a',
                'parent': '123',
                'timestamp': 123,
            }
        ]),
        '{"messages": {"0": {"timestamp": "must be of datetime type"}}}',
    ),
]


@pytest.mark.parametrize('data,exc', [(v[1], v[2]) for v in bad_data], ids=[v[0] for v in bad_data])
async def test_publish_misshaped_data(controller, timestamp, data, exc):
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, timestamp=timestamp, remote=True)
    with pytest.raises(BadDataException) as excinfo:
        await controller.act(a, data=data)
    assert excinfo.value.args[0] == exc
    assert len(controller.ds.data) == 0


async def test_wrong_hash(controller, timestamp):
    w_con_id = con_id + '+wrong'
    a = Action('testing@example.com', w_con_id, Verbs.ADD, Components.CONVERSATIONS, timestamp=timestamp, remote=True)
    with pytest.raises(BadHash) as excinfo:
        await controller.act(a, data=deepcopy(correct_data))
    assert excinfo.value.args[0] == 'provided hash {} does not match computed hash {}'.format(w_con_id, con_id)
    assert len(controller.ds.data) == 0
