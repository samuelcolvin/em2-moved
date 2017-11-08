import pytest

from ..conftest import CloseToNow


class TestAct:
    @pytest.fixture(autouse=True)
    def set_fixtures(self, cli, pub_conv, url, get_conv, act_headers):
        self.cli = cli
        self.conv = pub_conv
        self.url = url
        self.get_conv = get_conv
        self.act_headers = act_headers

    async def test_mod_message(self):
        second_msg_key = 'msg-secondmessagekey'
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item=second_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert obj['messages'][1]['body'] == 'foobar'

        url_ = self.url('act', conv=self.conv.key, component='message', verb='modify', item=second_msg_key)
        r = await self.cli.post(url_, data='different content',
                                headers=self.act_headers(parent=self.act_headers.action_stack[0]))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 3
        assert obj['messages'][1]['body'] == 'different content'

    async def test_no_parent(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item='msg-secondmessagekey')
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers())
        assert r.status == 400, await r.text()
        assert 'parent may not be null when adding a message' == await r.text()

    async def test_lock_unlock_message(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='lock', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 2
        assert {
            'actor': 'test@already-authenticated.com',
            'body': None,
            'component': 'message',
            'key': '1-------------------',
            'message': self.conv.first_msg_key,
            'parent': 'pub-add-message-1234',
            'participant': None,
            'ts': CloseToNow(),
            'verb': 'lock'
        } == obj['actions'][1]

        url_ = self.url('act', conv=self.conv.key, component='message', verb='lock', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='1-------------------'))
        assert r.status == 400, await r.text()
        assert 'you may not re-lock or re-unlock a message' == await r.text()
        url_ = self.url('act', conv=self.conv.key, component='message', verb='unlock', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='1-------------------'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 3
        assert obj['actions'][2]['verb'] == 'unlock'

    async def test_delete_recover_message(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='delete', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 2
        assert obj['actions'][1]['message'] == self.conv.first_msg_key
        assert obj['actions'][1]['verb'] == 'delete'
        assert len(obj['messages']) == 1
        assert obj['messages'][0]['deleted'] is True
        assert obj['messages'][0]['body'] == 'this is the message'

        url_ = self.url('act', conv=self.conv.key, component='message', verb='modify', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent=self.act_headers.action_stack[0]))
        assert r.status == 400, await r.text()
        assert 'message must be recovered before modification' == await r.text()

        url_ = self.url('act', conv=self.conv.key, component='message', verb='recover', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent=self.act_headers.action_stack[1]))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 3
        assert len(obj['messages']) == 1
        assert obj['messages'][0]['deleted'] is False
        assert obj['messages'][0]['body'] == 'this is the message'

        url_ = self.url('act', conv=self.conv.key, component='message', verb='modify', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent=self.act_headers.action_stack[0]))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 4
        assert len(obj['messages']) == 1
        assert obj['messages'][0]['deleted'] is False
        assert obj['messages'][0]['body'] == 'foobar'

    async def test_recover_not_deleted(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='recover', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 400, await r.text()
        assert 'message cannot be recovered as it is not deleted' == await r.text()

    async def test_delete_participant(self):
        r = await self.cli.post(
            self.url('act', conv=self.conv.key, component='participant', verb='add', item='foobar@example.com'),
            data='foobar',
            headers=self.act_headers(parent='pub-add-message-1234')
        )
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['participants']) == 2
        assert len(obj['actions']) == 2
        r = await self.cli.post(
            self.url('act', conv=self.conv.key, component='participant', verb='delete', item='foobar@example.com'),
            data='foobar',
            headers=self.act_headers()
        )
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['participants']) == 1
        assert len(obj['actions']) == 3

    async def test_add_child_message(self):
        second_msg_key = 'msg-secondmessagekey'
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item=second_msg_key)
        r = await self.cli.post(
            url_,
            data='foobar',
            headers=self.act_headers(parent='pub-add-message-1234', relationship='child')
        )
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 2
        assert [
            {
                'after': None,
                'body': 'this is the message',
                'format': 'markdown',
                'deleted': False,
                'key': 'msg-firstmessagekeyx',
                'relationship': None
            },
            {
                'after': 'msg-firstmessagekeyx',
                'body': 'foobar',
                'format': 'markdown',
                'deleted': False,
                'key': 'msg-secondmessagekey',
                'relationship': 'child'
            }
        ] == obj['messages']

    async def test_add_multiple_child_message(self):
        second_msg_key = 'msg-secondmessagekey'
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item=second_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        m2_action_key = self.act_headers.action_stack[0]

        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item='msg-third-messagekey')
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent=m2_action_key))
        assert r.status == 201, await r.text()

        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item='msg-fourthmessagekey')
        headers = self.act_headers(parent=m2_action_key, relationship='child')
        r = await self.cli.post(url_, data='foobar', headers=headers)
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert [
            {
                'after': None,
                'body': 'this is the message',
                'deleted': False,
                'format': 'markdown',
                'key': 'msg-firstmessagekeyx',
                'relationship': None
            },
            {
                'after': 'msg-firstmessagekeyx',
                'body': 'foobar',
                'deleted': False,
                'format': 'markdown',
                'key': 'msg-secondmessagekey',
                'relationship': 'sibling'
            },
            {
                'after': 'msg-secondmessagekey',
                'body': 'foobar',
                'deleted': False,
                'format': 'markdown',
                'key': 'msg-fourthmessagekey',
                'relationship': 'child'
            },
            {
                'after': 'msg-secondmessagekey',
                'body': 'foobar',
                'deleted': False,
                'format': 'markdown',
                'key': 'msg-third-messagekey',
                'relationship': 'sibling'
            }
        ] == obj['messages']

    async def test_msg_after_deleted(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='delete', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers(parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(parent=self.act_headers.action_stack[0]))
        assert r.status == 400, await r.text()
        assert 'you cannot add messages after a deleted message' == await r.text()

    async def test_add_msg_plain(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item='msg-secondmessagekey')
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(msg_format='html',
                                                                              parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert obj['messages'][1] == {
            'after': 'msg-firstmessagekeyx',
            'body': 'foobar',
            'deleted': False,
            'format': 'html',
            'key': 'msg-secondmessagekey',
            'relationship': 'sibling',
        }

    async def test_mod_message_format(self):
        obj = await self.get_conv(self.conv)
        assert obj['messages'][0]['format'] == 'markdown'

        url_ = self.url('act', conv=self.conv.key, component='message', verb='modify', item='msg-firstmessagekeyx')
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(msg_format='plain',
                                                                              parent='pub-add-message-1234'))
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert obj['messages'][0]['format'] == 'plain'

    async def test_no_msg_format(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item='msg-secondmessagekey')
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(msg_format=None))
        assert r.status == 400, await r.text()
        assert 'parent may not be null when adding a message' == await r.text()

    async def test_ts_updated(self, db_conn):
        updated_ts1 = await db_conn.fetchval('SELECT updated_ts FROM conversations')
        second_msg_key = 'msg-secondmessagekey'
        url_ = self.url('act', conv=self.conv.key, component='message', verb='add', item=second_msg_key)
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers(
            parent='pub-add-message-1234',
            timestamp='2000000000',
        ))
        assert r.status == 201, await r.text()
        updated_ts2 = await db_conn.fetchval('SELECT updated_ts FROM conversations')
        assert updated_ts1 < updated_ts2
        assert updated_ts2.year == 2033
