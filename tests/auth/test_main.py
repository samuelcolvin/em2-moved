from em2 import VERSION


async def test_index(cli, url):
    r = await cli.get(url('index'))
    assert r.status == 200, await r.text()
    assert f'em2 v{VERSION}:- auth interface\n' == await r.text()
