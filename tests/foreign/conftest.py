import pytest

from em2.foreign import create_foreign_app

from ..conftest import create_conversation


async def f_startup_modify_app(app):
    app['db'].conn = app['_conn']


@pytest.fixture
def cli(loop, settings, db_conn, test_client):
    app = create_foreign_app(settings)
    app['_conn'] = db_conn
    app.on_startup.append(f_startup_modify_app)
    return loop.run_until_complete(test_client(app))


@pytest.fixture
def conv(loop, db_conn):
    return loop.run_until_complete(create_conversation(db_conn, 'test@already-authenticated.com'))


@pytest.fixture
def get_conv(cli, url):
    async def _get_conv(_conv):
        r = await cli.get(url('get', conv=_conv.key), data='foobar', headers={
            'em2-auth': 'already-authenticated.com:123:whatever',
            'em2-participant': _conv.creator_address,
        })
        assert r.status == 200, await r.text()
        return await r.json()
    return _get_conv
