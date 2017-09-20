from datetime import datetime, timezone


def get_domain(address: str) -> str:
    """
    Parse an address and return its domain.
    """
    try:
        return address[address.index('@') + 1:] or None
    except (ValueError, AttributeError):
        pass


def to_utc_naive(dt: datetime):
    if dt.tzinfo and dt.tzinfo != timezone.utc:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)
