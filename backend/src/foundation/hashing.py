"""Password hashing utility."""

import hashlib

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns False rather than raising when bcrypt refuses the inputs. Two
    things reach this that are not "wrong password" but must look exactly like
    one:

    - **A password over 72 bytes.** bcrypt 5 raises `ValueError` instead of
      truncating. Login does not validate length — deliberately, since the rules
      belong on the fields that *set* a password — so before this, one long
      password produced a 500 for an account that exists and a 401 for one that
      does not. That difference is a user-enumeration oracle, and it undid the
      reason `AuthService.login` returns an identical error for a wrong email
      and a wrong password.
    - **A stored hash that is not a bcrypt hash.** A row seeded by hand or by a
      script that wrote the wrong column value would otherwise 500 forever for
      that one account, which is both unhelpful and, again, a signal that
      distinguishes it from every other account.

    Failing closed is the only safe direction here: an unreadable hash must
    never be treated as a match.
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")

    try:
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except ValueError:
        return False


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
