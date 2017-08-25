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


class FailedOutboundAuthentication(Em2Exception):
    pass


class PushError(Em2Exception):
    pass


class FallbackPushError(PushError):
    pass


class Em2ConnectionError(Em2Exception):
    pass
