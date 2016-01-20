import datetime
import pytest
from em2.base import Action, Verbs
from em2.common import Components
from em2.exceptions import BadDataException


async def test_publish_simple_conversation(controller):
    con_id = '0d35129317a6a6455609436c9aad1d11f2b0cb734d53b7222459d2452b25854f'
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, remote=True)
    data = {
        'creator': 'testing@example.com',
        'expiration': None,
        'messages': [
            {
                'author': 0,
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
    ds = controller.ds
    assert len(ds.data) == 0
    await controller.act(a, data=data)

    assert len(ds.data) == 1
    assert ds.data[0]['con_id'] == con_id
    assert ds.data[0]['subject'] == 'the subject'
    assert len(ds.data[0]['messages']) == 1
    assert list(ds.data[0]['messages'].values())[0]['body'] == 'the body'
    assert ds.data[0]['timestamp'] == datetime.datetime(2016, 1, 2)
    assert len(ds.data[0]['participants']) == 2


async def test_publish_invalid_args(controller):
    a = Action('testing@example.com', 'abc', Verbs.ADD, Components.CONVERSATIONS, remote=True)
    with pytest.raises(BadDataException):
        await controller.act(a, foo='bar')

    assert len(controller.ds.data) == 0


@pytest.mark.parametrize('data', [
    {
        'creator': 'testing@example.com',
        'expiration': None,
        'messages': [
            {
                'author': 0,
                'body': 'the body',
                'id': 'd21625d617b1e8eb8989aa3d57a5aae691f9ed2a',
                'parent': None,
                'timestamp': datetime.datetime(2016, 1, 1),
            }
        ],
        'participants': [('testing@example.com', 'full'), ('receiver@remote.com', 'write', 3)],
        'ref': 'the subject',
        'status': 'active',
        'subject': 'the subject',
        'timestamp': datetime.datetime(2016, 1, 2),
    },
    {
        'creator': 'testing@example.com',
        'expiration': None,
        'messages': [
            {
                'author': 0,
                'body': 'the body',
                'id': 'd21625d617b1e8eb8989aa3d57a5aae691f9ed2a',
                'parent': None,
                'timestamp': 123,
            }
        ],
        'participants': [('testing@example.com', 'full'), ('receiver@remote.com', 'write')],
        'ref': 'the subject',
        'status': 'active',
        'subject': 'the subject',
        'timestamp': datetime.datetime(2016, 1, 2),
    },
    {
        'foobar': 'whatever',
        'creator': 'testing@example.com',
        'expiration': None,
        'messages': [
            {
                'author': 0,
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
    },
    'hello',
    None,
    {'creator': 'testing@example.com'},
], ids=['missing_values', 'None', 'string', 'extra_key', 'bad_timestamp', 'list_extra_item'])
async def test_publish_misshaped_data(controller, data):
    con_id = '0d35129317a6a6455609436c9aad1d11f2b0cb734d53b7222459d2452b25854f'
    a = Action('testing@example.com', con_id, Verbs.ADD, Components.CONVERSATIONS, remote=True)
    with pytest.raises(BadDataException):
        await controller.act(a, data=data)

    assert len(controller.ds.data) == 0
