"""Password hashing with Argon2id.

New hashes use Argon2id with OWASP's recommended minimum parameters (19 MiB of
memory, 2 iterations, 1 lane): memory-hard enough to make GPU cracking
expensive while staying light on a small server. Hashes made by Werkzeug
before Argon2 was adopted (scrypt / PBKDF2) still verify, and callers rehash
them on the next successful sign-in.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from werkzeug.security import check_password_hash

_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)

# verifying against this when an account doesn't exist makes "no such user"
# take as long as "wrong password", so timing can't reveal registered emails
_DUMMY_HASH = _hasher.hash("runnify-timing-equaliser")


def hash_password(password):
    """Return an Argon2id hash of ``password``."""
    return _hasher.hash(password)


def verify_password(stored_hash, password):
    """Check ``password`` against ``stored_hash``.

    Args:
        stored_hash: An Argon2id hash, a legacy Werkzeug hash, or ``None`` when
            there is no account (the check still takes the usual time).
        password: The password to check.

    Returns:
        ``(matches, needs_rehash)``. ``needs_rehash`` is true when the password
        matched but the stored hash is legacy or uses outdated parameters.
    """
    if not stored_hash:
        _burn_time(password)
        return False, False
    if stored_hash.startswith("$argon2"):
        try:
            _hasher.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            return False, False
        return True, _hasher.check_needs_rehash(stored_hash)
    try:  # legacy Werkzeug hash (scrypt or pbkdf2)
        matches = check_password_hash(stored_hash, password)
    except ValueError:
        matches = False
    return matches, matches


def _burn_time(password):
    """Spend the same time as a real verification, then fail."""
    try:
        _hasher.verify(_DUMMY_HASH, password + "\0")
    except VerificationError:
        pass
