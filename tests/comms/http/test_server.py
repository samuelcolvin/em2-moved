from em2.core import Action, Verbs


async def test_add_message(client):
    action = Action('test@example.com', None, Verbs.ADD)
    conv_id = await client.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    headers = {
        'Authorization': 'Token 321',
        'Actor': 'test@example.com',
    }
    conv_ds = client.em2_ctrl.ds.new_conv_ds(conv_id, None)
    msg1_id = list(conv_ds.conv_obj['messages'])[0]
    data = '{"parent_id": "%s", "body": "reply"}' % msg1_id
    r = await client.post('/{}/messages/add/'.format(conv_id), data=data, headers=headers)
    assert r.status == 201
    content = await r.read()
    assert content == b'\n'


async def test_no_auth_header(client):
    r = await client.post('/123/messages/add/')
    assert r.status == 400
    content = await r.read()
    assert content == b'No "Authorization" header found\n'


async def test_no_actor_header(client):
    headers = {'Authorization': 'Token 321'}
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'No "Actor" header found\n'


async def test_missing_conversation(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b"BadDataException: missing a required argument: 'body'\n"


async def test_missing_conversation_valid_html(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    data = '{"body": "foobar", "parent_id": "123"}'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_json(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    data = 'foobar'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_valid_json_list(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    data = '[1, 2, 3]'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'request data is not a dictionary\n'
