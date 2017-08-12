class Em2Exception(Exception):
    pass


class ConfigException(Em2Exception):
    pass


class StartupException(Em2Exception):
    pass


class Em2AuthException(Em2Exception):
    pass


class FailedInboundAuthentication(Em2AuthException):
    pass


class FailedOutboundAuthentication(Em2AuthException):
    pass


class PushError(Em2Exception):
    pass


class FallbackPushError(PushError):
    pass


class Em2ConnectionError(Em2Exception):
    pass
