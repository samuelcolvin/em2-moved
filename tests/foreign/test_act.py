import pytest

from ..conftest import python_dict, timestamp_regex  # noqa


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
        r = await self.cli.post(url_, data='foobar', headers=self.act_headers())
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

    async def test_lock_unlock_message(self):
        url_ = self.url('act', conv=self.conv.key, component='message', verb='lock', item=self.conv.first_msg_key)
        r = await self.cli.post(url_, headers=self.act_headers())
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        assert len(obj['actions']) == 2
        assert {
            'actor': 'test@already-authenticated.com',
            'body': None,
            'component': 'message',
            'key': '1-------------------',
            'message': self.conv.first_msg_key,
            'parent': None,
            'participant': None,
            'ts': timestamp_regex,
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
        r = await self.cli.post(url_, headers=self.act_headers())
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
        r = await self.cli.post(url_, headers=self.act_headers())
        assert r.status == 400, await r.text()
        assert 'message cannot be recovered as it is not deleted' == await r.text()

    async def test_delete_participant(self):
        r = await self.cli.post(
            self.url('act', conv=self.conv.key, component='participant', verb='add', item='foobar@example.com'),
            data='foobar',
            headers=self.act_headers()
        )
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        # print(python_dict(obj))
        assert len(obj['participants']) == 2
        assert len(obj['actions']) == 2
        r = await self.cli.post(
            self.url('act', conv=self.conv.key, component='participant', verb='delete', item='foobar@example.com'),
            data='foobar',
            headers=self.act_headers()
        )
        assert r.status == 201, await r.text()
        obj = await self.get_conv(self.conv)
        # print(python_dict(obj))
        assert len(obj['participants']) == 1
        assert len(obj['actions']) == 3
