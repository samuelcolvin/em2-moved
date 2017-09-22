from aiohttp.web import HTTPBadRequest


class Em2Exception(Exception):
    pass


class ConfigException(Em2Exception):
    pass


class StartupException(Em2Exception):
    pass


class FailedInboundAuthentication(HTTPBadRequest, Em2Exception):
    def __init__(self, text: str):
        super().__init__(text='Authenticate failed: ' + text)


class FallbackPushError(Em2Exception):
    pass


class Em2ConnectionError(Em2Exception):
    pass
