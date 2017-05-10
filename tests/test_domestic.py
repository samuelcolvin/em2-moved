import base64
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from pydantic.datetime_parse import parse_datetime

from em2.domestic.middleware import SET_RECIPIENT_ID
from em2.utils.encoding import msg_encode


async def test_valid_cookie(clean_db, dclient, url):
    async with dclient.server.app['pg'].acquire() as conn:
        recipient_id = await conn.fetchval(SET_RECIPIENT_ID, 'testing@example.com')
        args = 'hash-1', recipient_id, 'Test Conversation', 'test'
        await conn.execute('INSERT INTO conversations (hash, creator, subject, ref) VALUES ($1, $2, $3, $4)', *args)
    r = await dclient.get(url('retrieve-list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    ts = parse_datetime(obj[0].pop('ts'))
    assert 0 < (datetime.now() - ts).total_seconds() < 1
    assert [{'hash': 'hash-1', 'draft_hash': None, 'subject': 'Test Conversation'}] == obj
    # assert 'Invalid token' in await r.text()


async def test_no_cookie(dclient, url):
    dclient.session.cookie_jar.clear()
    r = await dclient.get(url('retrieve-list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_invalid_cookie(dclient, url):
    data = {'address': 'testing@example.com'}
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(b'i am different and 32 bits long!'))
    settings = dclient.server.app['settings']
    cookies = {settings.COOKIE_NAME: fernet.encrypt(data).decode()}
    dclient.session.cookie_jar.update_cookies(cookies)
    r = await dclient.get(url('retrieve-list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


@pytest.mark.xfail
async def test_list_details_conv(dclient, conv_id, url):
    r = await dclient.get(url('retrieve-list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['conv_id'] == conv_id
    r = await dclient.get(url('retrieve-conv', conv=conv_id))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['messages'][0]['body'] == 'hello'


@pytest.mark.xfail
async def test_missing_conv(dclient, url):
    r = await dclient.get(url('retrieve-conv', conv='123'))
    assert r.status == 404, await r.text()
    text = await r.text()
    assert text.endswith('x not found')
