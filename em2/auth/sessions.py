import json
from datetime import datetime
from time import time

from em2.utils.web import JsonError, get_ip

GET_SESSION_SQL = """
SELECT s.active AS active, s.last_active AS last_active, u.id AS user_id
FROM auth_sessions AS s
JOIN auth_users AS u ON s.auth_user = u.id
WHERE s.token=$1
"""
UPDATE_SESSION_SQL = """
UPDATE auth_sessions SET last_active=CURRENT_TIMESTAMP, events=events || $1::JSONB
WHERE token=$2
"""
DEACTIVATE_SESSION_SQL = """
UPDATE auth_sessions SET last_active=CURRENT_TIMESTAMP, active=FALSE, events=events || $1::JSONB
WHERE token=$2
"""
SESSION_CACHE_TEMPLATE = 's:{}'


def session_event(request, action):
    return json.dumps({
        'ip': get_ip(request),
        'ts': int(time()),
        'ua': request.headers.get('User-Agent'),
        'ac': action
        # TODO include info about which session this is when multiple sessions are active
    })


async def activate_session(request, data):
    session_token, _, user_address = data.split(':', 2)
    user_id = await get_session_user(request.app, session_token, session_event(request, 'request'))
    if not user_id:
        raise JsonError.HTTPForbidden(error='session not active')
    request.update(
        session_token=session_token,
        user_address=user_address,
        user_id=user_id,
    )


async def get_session_user(app, session_token, event_data):
    session_cache = SESSION_CACHE_TEMPLATE.format(session_token).encode()
    with await app['redis'] as redis:
        d = await redis.get(session_cache)
        if d:
            return int(d)
        async with app['db'].acquire() as conn:
            r = await conn.fetchrow(GET_SESSION_SQL, session_token)
            if not r or not r['active']:
                return
            last_active, user_id = r['last_active'], r['user_id']

            expiry = last_active + app['settings'].auth_cookie_idle
            now = datetime.utcnow()

            if expiry > now:
                await conn.execute(UPDATE_SESSION_SQL, event_data, session_token)
                key_time = min(int((expiry - now).total_seconds()), 3600)
                await redis.setex(session_cache, key_time, str(user_id).encode())
                return user_id
            else:
                await conn.execute(DEACTIVATE_SESSION_SQL, event_data, session_token)


async def logout(request):
    event_data = session_event(request, 'logout')
    await request['conn'].execute(DEACTIVATE_SESSION_SQL, event_data, request['session_token'])

    session_cache = SESSION_CACHE_TEMPLATE.format(request['session_token']).encode()
    await request.app['redis'].delete(session_cache)
