import json
from datetime import datetime
from time import time

from em2.utils.web import JsonError, get_ip


GET_SESSION_SQL = """
SELECT active, last_active FROM auth_sessions WHERE token=$1
"""
UPDATE_SESSION_SQL = """
UPDATE auth_sessions SET last_active=CURRENT_TIMESTAMP, events=events || $1::JSONB
"""
DEACTIVATE_SESSION_SQL = """
UPDATE auth_sessions SET last_active=CURRENT_TIMESTAMP, active=FALSE, events=events || $1::JSONB
"""


def session_event(request, action):
    return json.dumps({
        'ip': get_ip(request),
        'ts': int(time()),
        'ua': request.headers.get('User-Agent'),
        'ac': action
        # TODO include info about which session this (when multiple sessions are active
    })


async def check_session_active(request, session):
    if not await check_update_session(request.app, session.token, session_event(request, 'auth request')):
        raise JsonError.HTTPForbidden(error='session not active')


async def check_update_session(app, session_token, event_data):
    session_cache = 's:{}'.format(session_token).encode()
    async with app['redis_pool'].get() as redis:
        if await redis.get(session_cache):
            return True
        async with app['db'].acquire() as conn:
            r = await conn.fetchrow(GET_SESSION_SQL, session_token)
            if not r or not r['active']:
                return False
            last_active = r['last_active']

            expiry = last_active + app['settings'].auth_cookie_idle
            session_active = expiry > datetime.utcnow()

            if session_active:
                await conn.execute(UPDATE_SESSION_SQL, event_data)
                await redis.setex(session_cache, 3600, b'1')
            else:
                await conn.execute(DEACTIVATE_SESSION_SQL, event_data)

            return session_active
