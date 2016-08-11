

class Em2Exception(Exception):
    pass


class ConfigException(Em2Exception):
    pass


class NotFoundException(Em2Exception):
    pass


class ConversationNotFound(NotFoundException):
    pass


class ComponentNotFound(NotFoundException):
    pass


class EventNotFound(NotFoundException):
    pass


class VerbNotFound(NotFoundException):
    pass


class BadHash(Em2Exception):
    pass


class DataConsistencyException(Em2Exception):
    pass


class InsufficientPermissions(Em2Exception):
    pass


class ComponentLocked(Em2Exception):
    pass


class ComponentNotLocked(Em2Exception):
    pass


class BadDataException(Em2Exception):
    pass


class MisshapedDataException(BadDataException):
    pass


class InvalidEmail(Em2Exception):
    pass


class Em2AuthException(Em2Exception):
    pass


class FailedInboundAuthentication(Em2AuthException):
    pass


class PlatformForbidden(Em2AuthException):
    pass


class DomainPlatformMismatch(Em2AuthException):
    pass


class FailedOutboundAuthentication(Em2AuthException):
    pass


class Em2ConnectionError(Em2Exception):
    pass
