"""
Views dedicated to propagation of data between platforms.
"""
import logging

import pytz
from aiohttp import web
from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden

# from em2.core import Action
from em2.exceptions import DomainPlatformMismatch, Em2Exception, FailedInboundAuthentication, PlatformForbidden
from em2.utils.datetime import from_unix_ms
from em2.utils.encoding import MSGPACK_CONTENT_TYPE, msg_decode, msg_encode

logger = logging.getLogger('em2.foreign.views')


def get_ip(request):
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip


def _get_headers(request_headers, spec):
    valid_headers = {}
    errors = []
    for h, required, *validators in spec:
        name = 'em2-' + h.replace('_', '-')
        value = request_headers.get(name, None)
        if value:
            if validators:
                v = validators[0]
                try:
                    value = v(value, **valid_headers)
                except ValueError as e:
                    errors.append((name, e))
                    continue
            valid_headers[h] = value
        elif required:
            errors.append((name, 'missing'))

    if errors:
        msg = '\n'.join(f'{name}: {error}' for name, error in errors)
        raise HTTPBadRequest(text=f'Invalid Headers:\n{msg}\n')
    return valid_headers


# headers and whether they're required
AUTH_HEADERS = [
    ('platform', True),
    ('timestamp', True, lambda v, **others: int(v)),
    ('signature', True),
]


async def authenticate(request):
    logger.info('authentication request from %s', get_ip(request))
    headers = _get_headers(request.headers, AUTH_HEADERS)
    logger.info('authentication data: %s', headers)

    auth = request.app['authenticator']
    try:
        key = await auth.authenticate_platform(headers['platform'], headers['timestamp'], headers['signature'])
    except FailedInboundAuthentication as e:
        logger.info('failed inbound authentication: %s', e)
        raise HTTPBadRequest(text=e.args[0] + '\n') from e
    return web.Response(text='ok\n', status=201, headers={'em2-key': key})


def validate_timezone(v, **others):
    try:
        return pytz.timezone(v)
    except pytz.UnknownTimeZoneError as e:
        raise ValueError(f'Unknown timezone "{v}"') from e


def validate_timestamp(v, **others):
    return from_unix_ms(int(v)).replace(tzinfo=others.get('timezone', pytz.utc))


ACT_HEADERS = [
    ('auth', True),
    ('address', True),
    ('timezone', False, validate_timezone),
    ('timestamp', True, validate_timestamp),
    ('event_id', True),
    ('parent_event_id', False),
]


async def _parse_headers(headers, auth):
    platform_token = headers.pop('auth')
    try:
        platform = await auth.valid_platform_token(platform_token)
    except PlatformForbidden as e:
        raise HTTPForbidden(text='Invalid auth header\n') from e

    logger.info('action from %s', platform)
    address = headers.pop('address')
    address_domain = address[address.index('@') + 1:]
    try:
        await auth.check_domain_platform(address_domain, platform)
    except DomainPlatformMismatch as e:
        raise HTTPForbidden(text=e.args[0] + '\n') from e

    return address, headers


async def act(request):
    headers = _get_headers(request.headers, ACT_HEADERS)
    address, extra_headers = await _parse_headers(headers, request.app['authenticator'])

    timezone = headers.pop('timezone', pytz.utc)

    # TODO support json as well as msgpack
    body_data = await request.read()
    try:
        obj = msg_decode(body_data, tz=timezone)
    except ValueError as e:
        raise HTTPBadRequest(text='Error Decoding msgpack: {}\n'.format(e)) from e

    if not isinstance(obj, dict):
        raise HTTPBadRequest(text='request data is not a dictionary\n')

    conversation = request.match_info['conv']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    Action = request.app['...']  # FIXME big old bodge to keep linting passing
    action = Action(address, conversation, verb, component, item=item, **extra_headers)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **obj)
    except Em2Exception as e:
        raise HTTPBadRequest(text='{}: {}\n'.format(e.__class__.__name__, e))

    body = msg_encode(response) if response else b'\n'
    return web.Response(body=body, status=201, content_type=MSGPACK_CONTENT_TYPE)
