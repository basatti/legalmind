"""Password hashing utility."""

import bcrypt
import hashlib

def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)

# ---------------------------------------------------------------------------
# LEG-13: content fingerprints — a different job from password hashing above
# ---------------------------------------------------------------------------


def hash_content(content: bytes) -> str:
    """Fingerprint a file's bytes so identical content is recognisable.

    Deliberately NOT bcrypt. Password hashing is slow and salted on purpose, so
    the same password gives a different hash every time — exactly wrong here.
    This needs the opposite: fast, and identical input always giving identical
    output, so 'have I already ingested this?' has an answer.
    """
    return hashlib.sha256(content).hexdigest()
