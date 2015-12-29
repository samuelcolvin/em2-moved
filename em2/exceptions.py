

class Em2Exception(Exception):
    pass


class Em2NotFoundException(Em2Exception):
    pass


class ConversationNotFound(Em2NotFoundException):
    pass


class ComponentNotFound(Em2NotFoundException):
    pass


class VerbNotFound(Em2NotFoundException):
    pass


class InsufficientPermissions(Em2Exception):
    pass


class ComponentLocked(Em2Exception):
    pass


class ComponentNotLocked(Em2Exception):
    pass
