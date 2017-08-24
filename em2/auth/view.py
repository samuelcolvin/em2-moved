import bcrypt
from aiohttp.hdrs import METH_POST
from aiohttp.web import HTTPConflict, Response
from pydantic import EmailStr, constr

from em2.utils.web import View, WebModel, decrypt_token


class Invitation(WebModel):
    address: EmailStr
    first_name: constr(max_length=255) = None
    last_name: constr(max_length=255) = None
    recovery_address: EmailStr = None


class AcceptInvitationView(View):
    GET_USER_SQL = 'SELECT id FROM auth_users WHERE address = $1'
    CREATE_USER_SQL = """
    INSERT INTO auth_users (address, first_name, last_name, recovery_address, password_hash)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
    """

    async def call(self, request):
        token = self.request.query.get('token', '-')
        inv = decrypt_token(token, self.app, Invitation)
        user_exists = await self.conn.fetchval(self.GET_USER_SQL, inv.address)
        if user_exists:
            raise HTTPConflict(text='user with this address already exists')

        if request.method == METH_POST:
            # TODO get password and password_confirm
            password = 'foobar'
            hashed = bcrypt.hashpw(password, bcrypt.gensalt(self.app['settings'].auth_bcrypt_wf))
            # check with https://github.com/dwolfhub/zxcvbn-python
            user_id = await self.conn.fetchval(
                self.CREATE_USER_SQL,
                inv.address, inv.first_name, inv.last_name, inv.recovery_address, hashed
            )
            if not user_id:
                raise HTTPConflict(text='user with this address already exists')
            return Response(text='ok')
        else:
            return Response(text='please submit password')
