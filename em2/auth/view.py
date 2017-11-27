import logging
from secrets import compare_digest
from time import time
from urllib.parse import urlencode

import bcrypt
from aiohttp.hdrs import METH_POST
from aiohttp.web import HTTPOk, HTTPTemporaryRedirect
from cryptography.fernet import InvalidToken
from pydantic import EmailStr, constr, validator
from zxcvbn import zxcvbn

from em2.utils import get_domain
from em2.utils.encoding import msg_decode
from em2.utils.web import View as _View
from em2.utils.web import JsonError, WebModel, get_ip, json_response, raw_json_response

from .sessions import logout, session_event

logger = logging.getLogger('em2.auth.views')


class Password(WebModel):
    password: constr(max_length=72)


class View(_View):
    CREATE_SESSION_SQL = """
    INSERT INTO auth_sessions (auth_user, events) VALUES ($1, ARRAY[$2::JSONB])
    RETURNING token
    """

    async def get_password_hash(self):
        # repeat password confirmation should be done in js
        password = Password(**await self.request_json()).password
        result = zxcvbn(password)
        if result['score'] < 2:
            raise JsonError.HTTPBadRequest(
                msg='password not strong enough',
                feedback=result['feedback'],
            )
        else:
            hashb = bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.settings.auth_bcrypt_work_factor))
            return hashb.decode()

    def set_cookie(self, response, cookie):
        response.set_cookie(self.settings.cookie_name, cookie, secure=self.settings.secure_cookies, httponly=True)

    async def response_create_session(self, user_id, user_address, action, **json_data):
        r = json_response(**json_data)
        token = await self.conn.fetchval(self.CREATE_SESSION_SQL, user_id, session_event(self.request, action))
        expires = int(time())
        cookie = self.app['session_fernet'].encrypt(f'{token}:{expires}:{user_address}'.encode()).decode()
        self.set_cookie(r, cookie)
        return r


class LoginView(View):
    # TODO enforce Same-Origin, json Content-Type, Referrer
    class LoginForm(WebModel):
        address: EmailStr
        password: constr(max_length=72)
        grecaptcha: constr(min_length=20, max_length=1000) = None

    GET_USER_HASH_SQL = """
    SELECT u.id, n.domain, u.password_hash FROM auth_users as u
    JOIN auth_nodes AS n ON u.node = n.id
    WHERE u.address = $1
    """

    async def _check_grecaptcha(self, grecaptcha_response, ip_address):
        data = dict(
            secret=self.settings.grecaptcha_secret,
            response=grecaptcha_response,
            remoteip=ip_address
        )
        data = urlencode(data).encode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with self.app['session'].post(self.settings.grecaptcha_url, data=data, headers=headers) as r:
            assert r.status == 200
            data = await r.json()
        # could check hostname here
        if data['success'] is not True:
            raise JsonError.HTTPBadRequest(error='invalid captcha')

    async def call(self, request):
        ip_address = get_ip(request)
        key = b'login:%s' % ip_address.encode()
        with await self.app['redis'] as redis:
            if request.method == METH_POST:
                login_attempts = int(await redis.incr(key))
                if login_attempts == 1:
                    # set expires on the first login attempt
                    await redis.expire(key, 60)
                captcha_required = login_attempts > self.settings.easy_login_attempts

                form = self.LoginForm(**await self.request_json())
                form.address = form.address.lower()  # TODO move to model clean method
                if captcha_required:
                    if form.grecaptcha:
                        await self._check_grecaptcha(form.grecaptcha, ip_address)
                    else:
                        raise JsonError.HTTPTooManyRequests(error='captcha required', captcha_required=True)

                r = await self.conn.fetchrow(self.GET_USER_HASH_SQL, form.address)
                # by always checking the password even if the address is not found we rule out use of
                # timing attack to check if users exist
                if r:
                    user_id, node_domain, password_hash = r
                else:
                    user_id, node_domain, password_hash = 0, '-', self.app['alt_pw_hash']

                if bcrypt.checkpw(form.password.encode(), password_hash.encode()):
                    return await self.response_create_session(
                        user_id,
                        form.address,
                        'login',
                        msg='login successful',
                        node_url=f'{request.scheme}://{node_domain}',
                    )
                else:
                    raise JsonError.HTTPUnauthorized(
                        error='invalid credentials',
                        captcha_required=login_attempts >= self.settings.easy_login_attempts
                    )
            else:
                return json_response(
                    msg='login',
                    # note the ">=" here vs ">" above since this time the value is not incremented
                    captcha_required=int(await redis.get(key) or b'0') >= self.settings.easy_login_attempts,
                )


class UpdateSession(View):
    async def call(self, request):
        token, user_address = request['session_token'], request['user_address']
        cookie = self.app['session_fernet'].encrypt(f'{token}:{int(time())}:{user_address}'.encode()).decode()
        redirect_to = request.query.get('r')
        r = HTTPTemporaryRedirect(location=redirect_to) if redirect_to else HTTPOk(text='ok')
        self.set_cookie(r, cookie)
        raise r


class LogoutView(View):
    async def call(self, request):
        await logout(request)
        r = json_response(msg='logout successful')
        r.del_cookie(self.settings.cookie_name)
        return r


class AcceptInvitationView(View):
    class Invitation(WebModel):
        address: EmailStr
        first_name: constr(max_length=255) = None
        last_name: constr(max_length=255) = None
        recovery_address: EmailStr = None

        @validator('address')
        def address_lower(cls, v):
            return v.lower()

    GET_USER_SQL = 'SELECT id FROM auth_users WHERE address = $1'
    CREATE_USER_SQL = """
    INSERT INTO auth_users (node, address, first_name, last_name, recovery_address, password_hash)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (address) DO NOTHING RETURNING id
    """
    GET_NODE_DOMAIN_SQL = 'SELECT domain FROM auth_nodes WHERE id = $1'

    def decrypt_token(self, token: str):
        try:
            raw_data = self.app['invitation_fernet'].decrypt(token.encode())
        except InvalidToken:
            raise JsonError.HTTPForbidden(error='Invalid token')
        try:
            data = msg_decode(raw_data)
            return self.Invitation(**data)
        except (ValueError, TypeError):
            # This shouldn't happen
            raise JsonError.HTTPInternalServerError(error='bad token data')

    async def call(self, request):
        token = self.request.query.get('token', '-')
        inv: self.Invitation = self.decrypt_token(token)
        if get_domain(inv.address) not in self.settings.auth_local_domains:
            raise JsonError.HTTPBadRequest(error='address domain not permitted')
        user_exists = await self.conn.fetchval(self.GET_USER_SQL, inv.address)
        if user_exists:
            raise JsonError.HTTPConflict(text='user with this address already exists')

        if request.method == METH_POST:
            pw_hash = await self.get_password_hash()
            user_id = await self.conn.fetchval(
                self.CREATE_USER_SQL,
                self.app['default_node_id'], inv.address, inv.first_name, inv.last_name, inv.recovery_address, pw_hash
            )
            if not user_id:
                raise JsonError.HTTPConflict(text='user with this address already exists')

            node_domain = await self.conn.fetchval(self.GET_NODE_DOMAIN_SQL, self.app['default_node_id'])
            return await self.response_create_session(
                user_id,
                inv.address,
                'user created',
                status_=201,
                msg='user created',
                node_url=f'{request.scheme}://{node_domain}',
            )
        else:
            return json_response(
                msg='please submit password',
                fields=inv.dict(),
            )


class AccountView(View):
    user_details_sql = """
    SELECT address, first_name, last_name, otp_secret, recovery_address
    FROM auth_users
    WHERE id = $1
    """

    async def call(self, request):
        # TODO add other available accounts
        data = dict(await self.fetchrow404(self.user_details_sql, self.request['user_id']))
        data['otp_enabled'] = bool(data.pop('otp_secret'))
        return json_response(**data)


class SessionsView(View):
    sessions_sql = """
    SELECT to_json(t)
    FROM (
      SELECT active, last_active, events
      FROM auth_sessions
      WHERE auth_user=$1
      ORDER BY last_active DESC
    ) t;
    """

    async def call(self, request):
        s = await self.conn.fetchval(self.sessions_sql, self.request['user_id'])
        return raw_json_response(s)


class CheckUserNodeView(View):
    """
    Internal only view for em2 nodes to find out if an address is "local" to them.

    Note: this approach to resolving node for an address doesn't use DNS records, is this a good idea?
    It means local messaging should work without correct DNS records which is good, but it could cause other problems.
    """
    GET_USER_SQL = """
    SELECT 1 FROM auth_users as u
    JOIN auth_nodes AS n ON u.node = n.id
    WHERE u.address = $1 AND n.domain = $2
    """

    class NodeModel(WebModel):
        address: str
        domain: str

    async def call(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not compare_digest(self.settings.auth_node_secret, auth_header):
            logger.warning('invalid auth header: "%s"', auth_header)
            raise JsonError.HTTPForbidden(error='invalid auth header')

        m = self.NodeModel(**await self.request_json())
        v = await self.conn.fetchval(self.GET_USER_SQL, m.address, m.domain)
        return json_response(local=bool(v))
