import json
from urllib.parse import urlencode

import bcrypt
from aiohttp.hdrs import METH_POST
from aiohttp.web import HTTPBadRequest, HTTPConflict, HTTPTooManyRequests
from pydantic import EmailStr, constr
from zxcvbn import zxcvbn

from em2.utils.web import JSON_CONTENT_TYPE, View, WebModel, decrypt_token, get_ip, json_response


class JsonHTTPBadRequest(HTTPBadRequest):
    def __init__(self, **data):
        super().__init__(text=json.dumps(data), content_type=JSON_CONTENT_TYPE)


class AuthView(View):
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
            hashb = bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.app['settings'].auth_bcrypt_work_factor))
            return hashb.decode()

    # async def response_set_cookie(self, msg):
    #     r = json_response(msg=msg)
    #     r.set_cookie(self.app['settings'].cookie_name, token, secure=not self.app['settings'].DEBUG, httponly=True)
    #     return r


class LoginView(AuthView):
    # TODO enforce Same-Origin, json Content-Type, Referrer
    class LoginForm(WebModel):
        address: EmailStr
        password: constr(max_length=72)
        grecaptcha: constr(min_length=20, max_length=1000)

    GET_USER_HASH_SQL = 'SELECT password_hash FROM auth_users WHERE address = $1'

    async def _check_grecaptcha(self, grecaptcha_response, ip_address):
        data = dict(
            secret=self.app['settings'].grecaptcha_secret,
            response=grecaptcha_response,
            remoteip=ip_address
        )
        data = urlencode(data).encode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with self.app['session'].post(self.app['settings'].grecaptcha_url, data=data, headers=headers) as r:
            assert r.status == 200
            data = await r.json()
        # could check hostname here
        if data['success'] is not True:
            raise JsonHTTPBadRequest(error='invalid captcha')

    async def call(self, request):
        ip_address = get_ip(request)
        key = b'login:%s' % ip_address.encode()
        captcha_required = False
        async with self.app['redis_pool'].get() as redis:
            if await redis.get(key):
                captcha_required = True
            else:
                await redis.setex(key, 60, b'1')
        if request.method == METH_POST:
            form = self.LoginForm(**await self.request_json())
            if captcha_required and not form.grecaptcha:
                if not form.grecaptcha:
                    raise HTTPTooManyRequests(text='captcha required')
                await self._check_grecaptcha(form.grecaptcha, ip_address)

            password_hash = await self.fetchval404(self.GET_USER_HASH_SQL, form.address)
            if bcrypt.checkpw(form.password, password_hash.encode()):
                return json_response(msg='login successful')
            else:
                raise JsonHTTPBadRequest(error='password incorrect')
        else:
            return json_response(
                msg='login',
                captcha_required=captcha_required,
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
        inv = decrypt_token(token, self.app, self.Invitation)
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
            # TODO log the user in here
            return json_response(msg='user created')
        else:
            return json_response(
                msg='please submit password',
                fields=inv.values()
            )
