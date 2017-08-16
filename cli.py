#!/usr/bin/env python3.6
import json
import re
import sys
from functools import partial

try:
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
    print('you need to: pip install -U click msgpack requests cryptography pygments')
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
    try:
        content = highlight_data(r.json())
    except ValueError:
        content = f'"{r.text}"'
    print(f"""\
{dim('request url', fmt='{}:')}     {green(r.request.url)}
{dim('request method', fmt='{}:')}  {green(r.request.method)}
{dim('request headers', fmt='{}:')}
{format_dict(r.request.headers)}
{dim('request time', fmt='{}:')}    {green(r.elapsed.total_seconds() * 1000, fmt='{:.0f}ms')}

{dim('response status', fmt='{}:')} {green(r.status_code)}
{dim('response headers', fmt='{}:')}
{format_dict(r.headers)}
{dim('response content', fmt='{}:')}
{content}
""")


def msg_encode(data):
    return msgpack.packb(data, use_bin_type=True)


def get_session(ctx):
    data = {'address': ctx.obj['address']}
    data = msg_encode(data)
    fernet = Fernet(ctx.obj['session_key'])
    session = requests.Session()
    session.cookies.set('em2session', fernet.encrypt(data).decode())
    return session


def url(ctx, uri):
    url = '{0[proto]}://{0[platform]}/'.format(ctx.obj)
    return url + uri.lstrip('/')


@click.group()
@click.pass_context
@click.option('--proto', default='https', envvar='EM2_COMMS_PROTO', help='env variable: EM2_COMMS_PROTO')
@click.option('--platform', default='localhost:5000', envvar='EM2_LOCAL_DOMAIN', help='env variable: EM2_LOCAL_DOMAIN')
@click.option('--session-key', default='testing', envvar='EM2_SECRET_SESSION_KEY',
              help='env variable: EM2_SECRET_SESSION_KEY')
@click.option('--address', default='testing@example.com', envvar='USER_ADDRESS',
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


@cli.command()
@click.pass_context
def list(ctx):
    session = get_session(ctx)
    r = session.get(url(ctx, '/d/'))
    print_response(r)


@cli.command()
@click.pass_context
@click.option('--subject', default='Test Message')
@click.option('--body', default='This is a message')
@click.argument('participants', nargs=-1)
def create(ctx, subject, body, participants):
    data = {
        'subject': subject,
        'message': body,
        'participants': participants or ('participant@example.com',),
    }
    session = get_session(ctx)
    r = session.post(url(ctx, '/d/create/'), json=data)
    print_response(r)


@cli.command()
@click.pass_context
@click.argument('conversation')
def get(ctx, conversation):
    session = get_session(ctx)
    r = session.get(url(ctx, f'/d/c/{conversation}/'))
    print_response(r)


if __name__ == '__main__':
    cli()
