

class Em2Exception(Exception):
    pass


class Em2NotFoundException(Em2Exception):
    pass


class ConversationNotFound(Em2NotFoundException):
    pass


class ComponentNotFound(Em2NotFoundException):
    pass
