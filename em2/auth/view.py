import json
from urllib.parse import urlencode

import bcrypt
from aiohttp.hdrs import METH_POST
from aiohttp.web import HTTPBadRequest, HTTPConflict, HTTPForbidden, HTTPTooManyRequests
from pydantic import EmailStr, constr
from zxcvbn import zxcvbn

from em2.utils.encoding import msg_encode
from em2.utils.web import JSON_CONTENT_TYPE, View, WebModel, decrypt_token, get_ip, json_response


class _JsonHTTPError:
    def __init__(self, **data):
        super().__init__(text=json.dumps(data), content_type=JSON_CONTENT_TYPE)


class JsonHTTPBadRequest(_JsonHTTPError, HTTPBadRequest):
    pass


class JsonHTTPForbidden(_JsonHTTPError, HTTPForbidden):
    pass


class JsonHTTPTooManyRequests(_JsonHTTPError, HTTPTooManyRequests):
    pass


class AuthView(View):
    CREATE_SESSION_SQL = """
    INSERT INTO auth_session (auth_user) VALUES ($1)
    RETURNING token
    """

    class Password(WebModel):
        password: constr(max_length=72)

    async def get_password_hash(self):
        # repeat password confirmation should be done in js
        password = self.Password(**await self.request_json()).password
        result = zxcvbn(password)
        if result['score'] < 2:
            raise JsonHTTPBadRequest(
                msg='password not strong enough',
                feedback=result['feedback'],
            )
        else:
            hashb = bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.settings.auth_bcrypt_work_factor))
            return hashb.decode()

    async def response_create_session(self, user_id, user_address, msg):
        r = json_response(msg=msg)
        token = await self.conn.fetchval(self.CREATE_SESSION_SQL, user_id)
        data = msg_encode(dict(
            token=str(token),
            address=user_address,
        ))
        token = self.app['fernet'].encrypt(data).decode()
        r.set_cookie(self.settings.cookie_name, token, secure=self.settings.secure_cookies, httponly=True)
        return r


class LoginView(AuthView):
    # TODO enforce Same-Origin, json Content-Type, Referrer
    class LoginForm(WebModel):
        address: EmailStr
        password: constr(max_length=72)
        grecaptcha: constr(min_length=20, max_length=1000) = None

    GET_USER_HASH_SQL = 'SELECT id, password_hash FROM auth_users WHERE address = $1'

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
            raise JsonHTTPBadRequest(error='invalid captcha')

    async def call(self, request):
        ip_address = get_ip(request)
        key = b'login:%s' % ip_address.encode()
        async with self.app['redis_pool'].get() as redis:

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
                        raise JsonHTTPTooManyRequests(error='captcha required', captcha_required=True)

                r = await self.conn.fetchrow(self.GET_USER_HASH_SQL, form.address)
                # by always checking the password even if the address is not found we rule out use of
                # timing attack to check if users exist
                if r:
                    user_id, password_hash = r
                else:
                    user_id, password_hash = 0, self.app['alt_pw_hash']

                if bcrypt.checkpw(form.password.encode(), password_hash.encode()):
                    return await self.response_create_session(user_id, form.address, 'login successful')
                else:
                    raise JsonHTTPForbidden(error='invalid credentials', captcha_required=captcha_required)
            else:
                return json_response(
                    msg='login',
                    # note the ">=" here vs ">" above since this time the value is not incremented
                    captcha_required=int(await redis.get(key) or b'0') >= self.settings.easy_login_attempts,
                )


class AcceptInvitationView(AuthView):
    class Invitation(WebModel):
        address: EmailStr
        first_name: constr(max_length=255) = None
        last_name: constr(max_length=255) = None
        recovery_address: EmailStr = None

    GET_USER_SQL = 'SELECT id FROM auth_users WHERE address = $1'
    CREATE_USER_SQL = """
    INSERT INTO auth_users (address, first_name, last_name, recovery_address, password_hash)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (address) DO NOTHING RETURNING id
    """

    async def call(self, request):
        token = self.request.query.get('token', '-')
        inv: self.Invitation = decrypt_token(token, self.app, self.Invitation)
        inv.address = inv.address.lower()  # TODO move to model clean method
        user_exists = await self.conn.fetchval(self.GET_USER_SQL, inv.address)
        if user_exists:
            raise HTTPConflict(text='user with this address already exists')

        if request.method == METH_POST:
            pw_hash = await self.get_password_hash()
            user_id = await self.conn.fetchval(
                self.CREATE_USER_SQL,
                inv.address, inv.first_name, inv.last_name, inv.recovery_address, pw_hash
            )
            if not user_id:
                raise HTTPConflict(text='user with this address already exists')
            return await self.response_create_session(user_id, inv.address, 'user created')
        else:
            return json_response(
                msg='please submit password',
                fields=inv.values()
            )
