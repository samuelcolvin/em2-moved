import json
import re

import click
import msgpack
import requests
from cryptography.fernet import Fernet
from pydantic.datetime_parse import parse_datetime
from pygments import highlight
from pygments.formatters.terminal256 import Terminal256Formatter
from pygments.lexers.data import JsonLexer
from pygments.lexers.html import HtmlLexer


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
    return highlight(data, lexer, formatter)


def format_dict(d):
    return '\n'.join(f'  {str(k) + ":":18} {v}' for k, v in d.items())


def print_response(r):
    try:
        content = highlight_data(r.json())
    except ValueError:
        content = r.text
    print(f"""\
request url: {r.request.url}
request method: {r.request.method}
request headers:
{format_dict(r.request.headers)}
response status: {r.status_code}
response headers:
{format_dict(r.headers)}
response content:
"{content}"\
""")


def msg_encode(data):
    return msgpack.packb(data, use_bin_type=True)


@click.group()
@click.pass_context
@click.option('--platform', default='localhost:8000', envvar='EM2_LOCAL_DOMAIN', help='env variable: EM2_LOCAL_DOMAIN')
@click.option('--session-key', default='testing', envvar='EM2_SECRET_SESSION_KEY',
              help='env variable: EM2_SECRET_SESSION_KEY')
@click.option('--address', default='testing@example.com', envvar='USER_ADDRESS',
              help='env variable: USER_ADDRESS')
def cli(ctx, platform, session_key, address):
    """
    Run em2 CLI.
    """
    ctx.obj = dict(
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
    data = {
        'address': ctx.obj['address']
    }
    data = msg_encode(data)
    fernet = Fernet(ctx.obj['session_key'])
    cookies = {
        'em2session': fernet.encrypt(data).decode()
    }
    r = requests.get(
        f'http://{ctx.obj["platform"]}/d/',
        cookies=cookies
    )
    print_response(r)


if __name__ == '__main__':
    cli()
