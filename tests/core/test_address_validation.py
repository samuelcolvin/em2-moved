import pytest

from em2.core.exceptions import InvalidEmail
from em2.core.validate import validate_address, parse_addresses


@pytest.mark.parametrize('address,valid', [
    ('foobar@example.com', True),
    ('s@muelcolvin.com', True),
    ('Samuel Colvin <s@muelcolvin.com>', True),
    ('foobar <foobar@example.com>', True),
    ('ñoñó@example.com', True),
    ('我買@example.com', True),
    ('甲斐黒川日本@example.com', True),
    ('чебурашкаящик-с-апельсинами.рф@example.com', True),
    ('उदाहरण.परीक्ष@domain.with.idn.tld', True),
    ('foo.bar@example.com', True),
    (' foo.bar@a.example.com', True),
    ('foo.bar@exam-ple.com ', True),
    ('f oo.bar@example.com ', False),
    ('foo.bar@exam\nple.com ', False),
    ('foobar', False),
    ('foobar <foobar@example.com', False),
    ('@example.com', False),
    ('foobar@example.co-m', False),
    ('foobar@.example.com', False),
    ('foobar@.com', False),
    ('test@domain.with.idn.tld.उदाहरण.परीक्षा', False),
    ('foo bar@example.com', False),
    ('foo@bar@example.com', False),
    ('\n@example.com', False),
    ('\r@example.com', False),
    ('\f@example.com', False),
    (' @example.com', False),
    ('\u0020@example.com', False),
    ('\u001f@example.com', False),
    ('"@example.com', False),
    ('\"@example.com', False),
    ('`@example.com', False),
    (',@example.com', False),
    ('foobar <foobar`@example.com>', False),
])
def test_address_validation(address, valid):
    if valid:
        validate_address(address)
    else:
        with pytest.raises(InvalidEmail):
            validate_address(address)


@pytest.mark.parametrize('address,expected_address', [
    ('foobar@example.com', 'foobar@example.com'),
    ('Samuel Colvin <s@muelcolvin.com>', 's@muelcolvin.com'),
    ('foobar <foobar@example.com>', 'foobar@example.com'),
    (' foo.bar@example.com', 'foo.bar@example.com'),
    ('foo.bar@example.com ', 'foo.bar@example.com'),
    ('foobar <foobar@example.com >', 'foobar@example.com'),
    ('foobar <foobar@example.com> ', 'foobar@example.com'),
])
def test_address_simplification(address, expected_address):
    assert validate_address(address) == expected_address


@pytest.mark.parametrize('addresses,expected_addresses', [
    ('foo@example.com, bar@domain.com', ['foo@example.com', 'bar@domain.com']),
    ('foo@example.com, whatever < bar@domain.com>', ['foo@example.com', 'bar@domain.com']),
    ('foo@example.com, bar@domain.com, , ', ['foo@example.com', 'bar@domain.com']),
])
def test_parse_addresses(addresses, expected_addresses):
    assert parse_addresses(addresses) == expected_addresses


def test_parse_addresses_raises():
    with pytest.raises(InvalidEmail):
        assert parse_addresses('foo@example.com, bar@domain .com')
