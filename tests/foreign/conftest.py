from datetime import datetime

import pytest

from em2.core import MsgFormat
from em2.foreign import create_foreign_app

from ..conftest import ConvInfo, shutdown_modify_app, startup_modify_app


@pytest.fixture
async def cli(loop, settings, db_conn, aiohttp_client, redis):
    app = create_foreign_app(settings)
    app['_conn'] = db_conn
    app.on_startup.append(startup_modify_app)
    app.on_shutdown.append(shutdown_modify_app)
    return await aiohttp_client(app)


@pytest.fixture
def conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator='test@already-authenticated.com'))


@pytest.fixture
def pub_conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator='test@already-authenticated.com', published=True))


GET_CONV_CREATOR = """
SELECT r.address FROM recipients AS r JOIN conversations AS c ON r.id = c.creator
WHERE c.key = $1
"""


@pytest.fixture
def get_conv(cli, url, db_conn):
    async def _get_conv(conv_):
        if isinstance(conv_, ConvInfo):
            creator_address = conv_.creator_address
            conv_ = conv_.key
        else:
            creator_address = await db_conn.fetchval(GET_CONV_CREATOR, conv_)
        if not creator_address:
            raise RuntimeError(f'no creator for conv {conv_}')
        r = await cli.get(url('get', conv=conv_), data='foobar', headers={
            'em2-auth': 'already-authenticated.com:123:whatever',
            'em2-participant': creator_address,
        })
        assert r.status == 200, await r.text()
        return await r.json()
    return _get_conv


@pytest.fixture
def act_headers(request):
    conv_ = request.getfixturevalue('conv' if 'conv' in request.fixturenames else 'pub_conv')

    class ActHeaders:
        def __init__(self):
            self.key_id = 0
            self.dft_actor = conv_.creator_address
            self.action_stack = []

        def __call__(self, **kwargs):
            self.key_id += 1
            key = (str(self.key_id) + '-' * 20)[:20]
            headers = {
                'em2-auth': 'already-authenticated.com:123:whatever',
                'em2-actor': self.dft_actor,
                'em2-timestamp': datetime.now().strftime('%s'),
                'em2-action-key': key,
                'em2-msg-format': MsgFormat.markdown
            }
            headers.update({f'em2-{k.replace("_", "-")}': v for k, v in kwargs.items()})
            headers = {k: v for k, v in headers.items() if v}
            self.action_stack.insert(0, key)
            return headers

    return ActHeaders()
