

async def test_no_auth_header(client):
    r = await client.post('/123/messages/add/')
    assert r.status == 400
    content = await r.read()
    assert content == b'No "Authorization" header found\n'


async def test_missing_conversation(client):
    headers = {'Authorization': 'Token 321'}
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_missing_conversation_valid_html(client):
    headers = {'Authorization': 'Token 321'}
    data = '{"key": "foobar"}'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_json(client):
    headers = {'Authorization': 'Token 321'}
    data = 'foobar'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_valid_json_list(client):
    headers = {'Authorization': 'Token 321'}
    data = '[1, 2, 3]'
    r = await client.post('/123/messages/add/', data=data, headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'request data is not a dictionary\n'
