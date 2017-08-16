import json
import re

import click
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
        raise RuntimeError(f'response not valid json:\n{r.text}')


formatter = Terminal256Formatter(style='vim')


def replace_data(m):
    dt = parse_datetime(m.group())
    # WARNING: this means the output is not valid json, but is more readable
    return f'{m.group()} ({dt:%a %Y-%m-%d %H:%M})'


def print_data(data, fmt='json'):
    if fmt == 'html':
        lexer = HtmlLexer()
    else:
        lexer = JsonLexer()
    if not isinstance(data, str):
        data = json.dumps(data, indent=2)
        data = re.sub('14\d{8,11}', replace_data, data)
    print(highlight(data, lexer, formatter))


def print_response(r, *, include=None, exclude=set()):
    data = {
        k: v for k, v in get_data(r).items()
        if k not in exclude and (not include or k in include)
    }
    print_data(data)


@click.group()
@click.pass_context
@click.option('--platform', default='localhost:8000', envvar='EM2_LOCAL_DOMAIN', help='env variable: EM2_LOCAL_DOMAIN')
@click.option('--session-key', default='testing', envvar='EM2_SECRET_SESSION_KEY',
              help='env variable: EM2_SECRET_SESSION_KEY')
def cli(ctx, platform, session_key):
    """
    Run em2 CLI.
    """
    ctx.obj = dict(
        platform=platform,
        session_key=session_key,
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
    r = requests.get('https://httpbin.org/get', headers=ctx.obj)
    print_response(r)


if __name__ == '__main__':
    cli()
