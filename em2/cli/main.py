import json
import re

import click
import requests
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
@click.option('--platform', required=True, envvar='EM2_PLATFORM', help='required, env variable: EM2_PLATFORM')
@click.option('--auth-token', required=True, envvar='EM2_AUTH_TOKEN', help='required, env variable: EM2_AUTH_TOKEN')
def cli(ctx, platform, auth_token):
    """
    Run em2 CLI.
    """
    ctx.obj = dict(
        platform=platform,
        auth_token=auth_token,
    )


@cli.command()
@click.pass_context
def list(ctx):
    r = requests.get('https://httpbin.org/get', headers=ctx.obj)
    print_response(r)


if __name__ == '__main__':
    cli()
