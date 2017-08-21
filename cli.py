#!/usr/bin/env python3.6
import asyncio
import json
import re
import sys
from functools import partial
from time import sleep

try:
    import aiohttp
    import click
    import msgpack
    import requests
    from cryptography.fernet import Fernet
    from pydantic.datetime_parse import parse_datetime
    from pygments import highlight
    from pygments.formatters.terminal256 import Terminal256Formatter
    from pygments.lexers.data import JsonLexer
    from pygments.lexers.html import HtmlLexer
except ImportError as e:
    print(f'Import Error: {e}')
    print('you need to: pip install -U aiohttp click msgpack-python requests cryptography pygments')
    sys.exit(1)


def get_data(r):
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f'response not valid json: status={r.status_code} content="{r.text}"')


formatter = Terminal256Formatter(style='vim')


def replace_data(m):
    dt = parse_datetime(m.group())
    # WARNING: this means the output is not valid json, but is more readable
    return f'{m.group()} ({dt:%a %Y-%m-%d %H:%M})'


def highlight_data(data, fmt='json'):
    if data is None:
        return 'null'
    if isinstance(data, bytes):
        data = data.decode()

    if fmt == 'json':
        try:
            data = json.loads(data)
        except ValueError:
            return f'"{data}"'

    if fmt == 'html':
        lexer = HtmlLexer()
    else:
        lexer = JsonLexer()

    if not isinstance(data, str):
        data = json.dumps(data, indent=2)
        data = re.sub('14\d{8,11}', replace_data, data)
    return highlight(data, lexer, formatter).rstrip('\n')


def style(s, pad=0, limit=1000, fmt='{}', **kwargs):
    s = fmt.format(s)
    return click.style(str(s).ljust(pad)[:limit], **kwargs)


green = partial(style, fg='green')
blue = partial(style, fg='blue')
red = partial(style, fg='red')
magenta = partial(style, fg='magenta')
yellow = partial(style, fg='yellow')
dim = partial(style, fg='white', dim=True)


def format_dict(d):
    return '\n'.join(f'  {blue(k, fmt="{}:")} {red(v)}' for k, v in d.items())


def print_response(r):
    print(f"""\
{dim('request url', fmt='{}:')}     {green(r.request.url)}
{dim('request method', fmt='{}:')}  {green(r.request.method)}
{dim('request headers', fmt='{}:')}
{format_dict(r.request.headers)}
{dim('request body', fmt='{}:')}
{highlight_data(r.request.body)}
{dim('request time', fmt='{}:')}    {green(r.elapsed.total_seconds() * 1000, fmt='{:.0f}ms')}

{dim('response status', fmt='{}:')} {green(r.status_code)}
{dim('response headers', fmt='{}:')}
{format_dict(r.headers)}
{dim('response content', fmt='{}:')}
{highlight_data(r.text)}
""")


def get_cookie(ctx):
    data = {'address': ctx.obj['address']}
    data = msgpack.packb(data, use_bin_type=True)
    fernet = Fernet(ctx.obj['session_key'])
    return 'em2session', fernet.encrypt(data).decode()


def make_session(ctx):
    session = requests.Session()
    session.cookies.set(*get_cookie(ctx))
    return session


def url(ctx, uri):
    url = '{0[proto]}://{0[platform]}/'.format(ctx.obj)
    return url + uri.lstrip('/')


@click.group()
@click.pass_context
@click.option('--proto', default='https', envvar='EM2_COMMS_PROTO', help='env variable: EM2_COMMS_PROTO')
@click.option('--platform', default='localhost:8000', envvar='EM2_LOCAL_DOMAIN', help='env variable: EM2_LOCAL_DOMAIN')
@click.option('--session-key', default='testing', envvar='EM2_SECRET_SESSION_KEY',
              help='env variable: EM2_SECRET_SESSION_KEY')
@click.option('--address', default='testing@localhost.example.com', envvar='USER_ADDRESS',
              help='env variable: USER_ADDRESS')
def cli(ctx, platform, proto, session_key, address):
    """
    Run em2 CLI.
    """
    ctx.obj = dict(
        proto=proto,
        platform=platform,
        session_key=session_key,
        address=address,
    )


@cli.command()
@click.pass_context
def genkey(ctx):
    print(f"""
    New secret key:

    export EM2_SECRET_SESSION_KEY="{Fernet.generate_key().decode()}"
    """)


@cli.command(name='list')
@click.pass_context
def list_(ctx):
    session = make_session(ctx)
    r = session.get(url(ctx, '/d/'))
    print_response(r)


@cli.command()
@click.pass_context
@click.option('--subject', default='Test Message')
@click.option('--body', default='This is a message')
@click.argument('participants', nargs=-1)
def create(ctx, subject, body, participants):
    participants = set(participants or ['participant@remote.example.com'])
    participants.add(ctx.obj['address'])
    data = {
        'subject': subject,
        'message': body,
        'participants': list(participants),
    }
    session = make_session(ctx)
    r = session.post(url(ctx, '/d/create/'), json=data)
    print_response(r)


@cli.command()
@click.pass_context
@click.argument('conversation')
def get(ctx, conversation):
    session = make_session(ctx)
    r = session.get(url(ctx, f'/d/c/{conversation}/'))
    print_response(r)


@cli.command()
@click.pass_context
@click.argument('conversation')
def publish(ctx, conversation):
    session = make_session(ctx)
    r = session.post(url(ctx, f'/d/publish/{conversation}/'))
    print_response(r)


def _get_details(ctx, session, conversation):
    r = session.get(url(ctx, f'/d/c/{conversation}/'))
    try:
        assert r.status_code == 200
        return r.json()
    except (AssertionError, ValueError):
        print_response(r)
        raise


@cli.group()
@click.pass_context
def add(ctx):
    pass


@add.command(name='message')
@click.pass_context
@click.option('--parent')
@click.argument('conversation')
@click.argument('body')
def add_message(ctx, parent, conversation, body):
    session = make_session(ctx)
    if not parent:
        conv_details = _get_details(ctx, session, conversation)
        actions = conv_details['actions'] or []
        try:
            parent = next(a for a in reversed(actions) if a['message'])['key']
        except StopIteration:
            print('no parent found, assuming no actions have occurred')

    post_data = {
        'body': body,
        'parent': parent,
    }

    r = session.post(url(ctx, f'/d/act/{conversation}/message/add/'), json=post_data)
    print_response(r)


@add.command(name='participant')
@click.pass_context
@click.argument('conversation')
@click.argument('address')
def add_participant(ctx, conversation, address):
    session = make_session(ctx)
    post_data = {'item': address}

    r = session.post(url(ctx, f'/d/act/{conversation}/participant/add/'), json=post_data)
    print_response(r)


@cli.group()
@click.pass_context
def modify(ctx):
    pass


@modify.command(name='message')
@click.pass_context
@click.option('--parent')
@click.argument('conversation')
@click.argument('item')
@click.argument('body')
def modify_message(ctx, parent, conversation, item, body):
    session = make_session(ctx)
    if not parent:
        conv_details = _get_details(ctx, session, conversation)
        actions = conv_details['actions'] or []
        try:
            parent = next(a for a in reversed(actions) if a['message'] == item)['key']
        except StopIteration:
            print('no parent found, assuming no actions have occurred')

    post_data = {
        'item': item,
        'body': body,
        'parent': parent,
    }

    r = session.post(url(ctx, f'/d/act/{conversation}/message/modify/'), json=post_data)
    print_response(r)


async def _watch(ctx):
    name, value = get_cookie(ctx)
    async with aiohttp.ClientSession(cookies={name: value}) as session:
        while True:
            try:
                print(f'connecting to ws...')
                async with session.ws_connect(url(ctx, '/d/ws/')) as ws:
                    print('websocket connected, waiting for messages...')
                    async for msg in ws:
                        if msg.tp == aiohttp.WSMsgType.ERROR:
                            # this happens when nginx times our, try reconnection
                            break
                        print(f'ws message {msg.tp!r} {highlight_data(msg.data)}')
            except aiohttp.WSServerHandshakeError as e:
                print(f'WSServerHandshakeError: {e}')
                print(f'headers: {e.headers}')

            print(yellow('ws connection error, reconnecting in 1 seconds...'))
            sleep(1)


@cli.command()
@click.pass_context
def watch(ctx):
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(_watch(ctx))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    cli()
