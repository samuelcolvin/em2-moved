from ..conftest import python_dict, timestamp_regex  # noqa


async def test_mod_message(cli, conv, url, get_conv, act_headers):
    second_msg_key = 'msg-secondmessagekey'
    url_ = url('act', conv=conv.key, component='message', verb='add', item=second_msg_key)
    r = await cli.post(url_, data='foobar', headers=act_headers())
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert obj['messages'][1]['body'] == 'foobar'

    url_ = url('act', conv=conv.key, component='message', verb='modify', item=second_msg_key)
    r = await cli.post(url_, data='different content', headers=act_headers(parent=act_headers.action_stack[0]))
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 2
    assert obj['messages'][1]['body'] == 'different content'


async def test_lock_unlock_message(cli, conv, url, get_conv, act_headers):
    url_ = url('act', conv=conv.key, component='message', verb='lock', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers())
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 1
    assert {
        'actor': 'test@already-authenticated.com',
        'body': None,
        'component': 'message',
        'key': '1-------------------',
        'message': conv.first_msg_key,
        'parent': None,
        'participant': None,
        'ts': timestamp_regex,
        'verb': 'lock'
    } == obj['actions'][0]

    url_ = url('act', conv=conv.key, component='message', verb='lock', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers(parent='1-------------------'))
    assert r.status == 400, await r.text()
    assert 'you may not re-lock or re-unlock a message' == await r.text()
    url_ = url('act', conv=conv.key, component='message', verb='unlock', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers(parent='1-------------------'))
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 2
    assert obj['actions'][1]['verb'] == 'unlock'


async def test_delete_recover_message(cli, conv, url, get_conv, act_headers):
    url_ = url('act', conv=conv.key, component='message', verb='delete', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers())
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 1
    assert obj['actions'][0]['message'] == conv.first_msg_key
    assert obj['actions'][0]['verb'] == 'delete'
    assert len(obj['messages']) == 1
    assert obj['messages'][0]['deleted'] is True
    assert obj['messages'][0]['body'] == 'this is the message'

    url_ = url('act', conv=conv.key, component='message', verb='modify', item=conv.first_msg_key)
    r = await cli.post(url_, data='foobar', headers=act_headers(parent=act_headers.action_stack[0]))
    assert r.status == 400, await r.text()
    assert 'message must be recovered before modification' == await r.text()

    url_ = url('act', conv=conv.key, component='message', verb='recover', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers(parent=act_headers.action_stack[1]))
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 2
    assert len(obj['messages']) == 1
    assert obj['messages'][0]['deleted'] is False
    assert obj['messages'][0]['body'] == 'this is the message'

    url_ = url('act', conv=conv.key, component='message', verb='modify', item=conv.first_msg_key)
    r = await cli.post(url_, data='foobar', headers=act_headers(parent=act_headers.action_stack[0]))
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    assert len(obj['actions']) == 3
    assert len(obj['messages']) == 1
    assert obj['messages'][0]['deleted'] is False
    assert obj['messages'][0]['body'] == 'foobar'


async def test_recover_not_deleted(cli, conv, url, get_conv, act_headers):
    url_ = url('act', conv=conv.key, component='message', verb='recover', item=conv.first_msg_key)
    r = await cli.post(url_, headers=act_headers())
    assert r.status == 400, await r.text()
    assert 'message cannot be recovered as it is not deleted' == await r.text()


async def test_delete_participant(cli, conv, url, get_conv, act_headers):
    r = await cli.post(
        url('act', conv=conv.key, component='participant', verb='add', item='foobar@example.com'),
        data='foobar',
        headers=act_headers()
    )
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    print(python_dict(obj))
    assert len(obj['participants']) == 2
    assert len(obj['actions']) == 1
    r = await cli.post(
        url('act', conv=conv.key, component='participant', verb='delete', item='foobar@example.com'),
        data='foobar',
        headers=act_headers()
    )
    assert r.status == 201, await r.text()
    obj = await get_conv(conv)
    # print(python_dict(obj))
    assert len(obj['participants']) == 1
    assert len(obj['actions']) == 2
