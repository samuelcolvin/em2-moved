import re

from em2.exceptions import InvalidEmail

PRETTY_REGEX = re.compile(r'^([\w ]*?) *<(.*)> *$')

# max length for domain name labels is 63 characters per RFC 1034
ADDRESS_REGEX = re.compile(r'^[^\s@\u0000-\u0020"\'`,]+@'
                           r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z0-9]{2,63})$', re.I)


def validate_address(value):
    """
    Brutally simple email address validation. Note unlike most email address validation, except:
    * raw ip address (literal) domain_parts are not allowed.
    * "John Doe <local_part@domain.com>" style "pretty" email addresses are processed, and the raw address returned
    * the local part check is extremely basic. This raises the possibility of unicode spoofing, but no better
        solution is really possible at this stage.
    * spaces are striped from the beginning and end of addresses but no error is raised

    See RFC 5322 but treat it with suspicion, there seems to exist no universally acknowledged test for a valid email!
    """
    m = re.search(PRETTY_REGEX, value)
    if m:
        name, value = m.groups()

    value = value.strip()

    if not ADDRESS_REGEX.match(value):
        raise InvalidEmail('The email address "{}" is not valid'.format(value))
    return value


def parse_addresses(s):
    """
    Validate a string of comma separated addresses, raise InvalidEmail or return list of addresses
    """
    return [validate_address(addr) for addr in s.split(',') if addr.strip()]
