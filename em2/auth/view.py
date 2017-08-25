import json

import bcrypt
from aiohttp.hdrs import METH_POST
from aiohttp.web import HTTPBadRequest, HTTPConflict
from pydantic import EmailStr, constr
from zxcvbn import zxcvbn

from em2.utils.web import JSON_CONTENT_TYPE, View, WebModel, decrypt_token, json_response


class JsonHTTPBadRequest(HTTPBadRequest):
    def __init__(self, **data):
        super().__init__(text=json.dumps(data), content_type=JSON_CONTENT_TYPE)


class Password(WebModel):
    password: constr(max_length=72)


class SetPasswordView(View):
    async def get_password_hash(self):
        # repeat password confirmation should be done in js
        password = Password(**await self.request_json()).password
        result = zxcvbn(password)
        if result['score'] < 2:
            JsonHTTPBadRequest(
                msg='password not strong enough',
                feedback=result['feedback'],
            )
        hashb = bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.app['settings'].auth_bcrypt_work_factor))
        return hashb.decode()


class AcceptInvitationView(SetPasswordView):
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
