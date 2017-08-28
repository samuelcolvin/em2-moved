#!/usr/bin/env python3.6
import asyncio
import json
import re
import sys
from functools import partial
from pathlib import Path
from subprocess import PIPE, run
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


@click.group()
@click.pass_context
@click.option('--domestic-url', default='http://localhost:8000/d/', envvar='EM2_DOMESTIC_URL',
              help='env variable: EM2_DOMESTIC_URL')
@click.option('--auth-url', default='http://localhost:8000/auth/', envvar='EM2_AUTH_URL',
              help='env variable: EM2_AUTH_URL')
@click.option('--auth-invitation-secret', default='you need to replace me with a real Fernet keyxxxxxxx=',
              envvar='EM2_AUTH_INVITATION_SECRET', help='env variable: EM2_AUTH_INVITATION_SECRET')
@click.option('--address', default='testing@localhost.example.com', envvar='USER_ADDRESS',
              help='env variable: USER_ADDRESS')
@click.option('--password', default='we-are-testing')
def cli(ctx, **kwargs):
    """
    Run em2 CLI.
    """
    ctx.obj = kwargs


@cli.command()
@click.pass_context
def gen_session_key(ctx):
    print(f"""
    New secret key:

    export EM2_SECRET_SESSION_KEY='{Fernet.generate_key().decode()}'
    """)


@cli.command()
@click.pass_context
def gen_dns_keys(ctx):
    # openssl genrsa -out private.pem 4096
    # openssl rsa -in private.pem -pubout > public.pem
    print('generating public and private keys for DNS validation....\n')
    private_key_file = 'em2-private.pem'
    run(['openssl', 'genrsa', '-out', private_key_file, '4096'], check=True)
    p = run(['openssl', 'rsa', '-in', private_key_file, '-pubout'], check=True, stdout=PIPE, encoding='utf8')
    public_key = re.sub(r'(?:-{3,}.*?-{3,}|\s)', '', p.stdout)

    print(f"""
    public and private keys generated, private key file is: {private_key_file}

    The public key should be set as a TXT record with value:

    v=em2key {public_key}

    (with no leading or trailing spaces)\n""")


@cli.command()
@click.pass_context
def create_account(ctx):
    fernet = Fernet(ctx.obj['auth_invitation_secret'].encode())
    data = dict(address=ctx.obj['address'], last_name='testing')
    token = fernet.encrypt(msgpack.packb(data, use_bin_type=True)).decode()
    session = requests.Session()
    url_ = url(ctx, '/accept-invitation/', auth=True) + f'?token={token}'
    r = session.post(url_, json={'password': ctx.obj['password']})
    print_response(r)


@cli.command(name='list')
@click.pass_context
def list_(ctx):
    session = make_session(ctx)
    r = session.get(url(ctx, '/list/'))
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
    r = session.post(url(ctx, '/create/'), json=data)
    print_response(r)


@cli.command()
@click.pass_context
@click.argument('conversation')
def get(ctx, conversation):
    session = make_session(ctx)
    r = session.get(url(ctx, f'/c/{conversation}/'))
    print_response(r)


@cli.command()
@click.pass_context
@click.argument('conversation')
def publish(ctx, conversation):
    session = make_session(ctx)
    r = session.post(url(ctx, f'/publish/{conversation}/'))
    print_response(r)


def _get_details(ctx, session, conversation):
    r = session.get(url(ctx, f'/c/{conversation}/'))
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
@click.option('--parent', '-p')
@click.option('--relationship', '-r', type=click.Choice(['sibling', 'child']))
@click.argument('conversation')
@click.argument('body')
def add_message(ctx, parent, relationship, conversation, body):
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
        'relationship': relationship,
    }

    r = session.post(url(ctx, f'/act/{conversation}/message/add/'), json=post_data)
    print_response(r)


@add.command(name='participant')
@click.pass_context
@click.argument('conversation')
@click.argument('address')
def add_participant(ctx, conversation, address):
    session = make_session(ctx)
    post_data = {'item': address}

    r = session.post(url(ctx, f'/act/{conversation}/participant/add/'), json=post_data)
    print_response(r)


@cli.group()
@click.pass_context
def modify(ctx):
    pass


@modify.command(name='message')
@click.pass_context
@click.option('--parent', '-p')
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

    r = session.post(url(ctx, f'/act/{conversation}/message/modify/'), json=post_data)
    print_response(r)


async def _watch(ctx):
    name, value = get_cookie(ctx)
    async with aiohttp.ClientSession(cookies={name: value}) as session:
        while True:
            try:
                print(f'connecting to ws...')
                async with session.ws_connect(url(ctx, '/ws/')) as ws:
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
    redirects = ' > '.join(f'{r_.request.method} {r_.url} {r_.status_code}' for r_ in r.history)

    print(f"""\
{dim('request url', fmt='{}:')}     {green(r.request.url)}
{dim('request method', fmt='{}:')}  {green(r.request.method)}
{dim('request headers', fmt='{}:')}
{format_dict(r.request.headers)}
{dim('request body', fmt='{}:')}
{highlight_data(r.request.body)}
{dim('request time', fmt='{}:')}    {green(r.elapsed.total_seconds() * 1000, fmt='{:.0f}ms')}

{redirects or '(no redirects)'}

{dim('response status', fmt='{}:')} {green(r.status_code)}
{dim('response headers', fmt='{}:')}
{format_dict(r.headers)}
{dim('response content', fmt='{}:')}
{highlight_data(r.text)}
""")


def make_session(ctx):
    session = requests.Session()
    cookie_path = Path('em2-cookie-{[address]}.json'.format(ctx.obj))
    if cookie_path.exists():
        with cookie_path.open() as f:
            cookies = json.load(f)

        for name, value in cookies.items():
            session.cookies.set(name, value)
    else:
        print('cookie file missing, logging in...')
        data = {'password': ctx.obj['password'], 'address': ctx.obj['address']}
        r = session.post(url(ctx, '/login/', auth=True), json=data)
        if r.status_code != 200:
            click.secho('Error logging in:\n', fg='red')
            print_response(r)
            sys.exit(1)

        print('login successful, saving cookie')
        with cookie_path.open('w') as f:
            json.dump(dict(session.cookies), f, indent=2)
    return session


def url(ctx, uri, auth=False):
    base = ctx.obj['auth_url'] if auth else ctx.obj['domestic_url']
    return base.rstrip('/') + '/' + uri.lstrip('/')


if __name__ == '__main__':
    cli()
