"""Backend foundation package — placeholder establishing the project layout."""

from foundation.hashing import hash_password, verify_password

__version__ = "0.1.0"


def hello() -> str:
    """Sanity-check function used by the example test."""
    return "Hello from backend"


__all__ = [
    "hello",
    "hash_password",
    "verify_password",
]
