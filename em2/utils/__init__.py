

def get_domain(address: str) -> str:
    """
    Parse an address and return its domain.
    """
    try:
        return address[address.index('@') + 1:] or None
    except (ValueError, AttributeError):
        pass
