"""Password hashing (Argon2id) and the password policy.

New hashes use Argon2id with OWASP's recommended minimum parameters (19 MiB of
memory, 2 iterations, 1 lane): memory-hard enough to make GPU cracking
expensive while staying light on a small server. Hashes made by Werkzeug
before Argon2 was adopted (scrypt / PBKDF2) still verify, and callers rehash
them on the next successful sign-in.

The policy follows NIST SP 800-63B: length matters more than composition
rules, so there are no "must contain a symbol" requirements. Instead,
passwords that are common (even with leetspeak or digits tacked on),
sequential, repetitive or built from the user's own name or email are refused.
"""

import contextlib
import re

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
    with contextlib.suppress(VerificationError):
        _hasher.verify(_DUMMY_HASH, password + "\0")


MIN_LENGTH = 12
MAX_LENGTH = 128

# Words at the heart of the most-breached passwords; "Password2024!" or "P@ssw0rd123"
# reduce to "password" once digits, symbols and leetspeak are stripped.
COMMON_WORDS = frozenset(
    """
    password passw passwd pass qwerty qwertyuiop asdfgh asdfghjkl zxcvbnm letmein welcome
    iloveyou admin administrator login football baseball soccer hockey basketball dragon
    monkey sunshine princess master shadow superman batman michael jordan charlie trustno
    starwars whatever freedom hello secret abc abcdef abcdefgh changeme default guest
    computer internet summer winter spring autumn love lovely flower tigger cheese pepper
    ginger killer hunter ranger runner running marathon jogging fitness spotify garmin
    runnify music playlist google apple samsung iphone liverpool arsenal chelsea united
    ireland dublin london england qazwsx qwertz azerty
    """.split()  # noqa: SIM905  (a word list reads better as text)
)

SEQUENCES = (
    "abcdefghijklmnopqrstuvwxyz",
    "zyxwvutsrqponmlkjihgfedcba",
    "01234567890123456789",
    "98765432109876543210",
    "qwertyuiopasdfghjklzxcvbnm",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik9ol0p",
)

_LEET = str.maketrans(
    {"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s", "5": "s", "7": "t"}
)


def password_problems(password, *, email="", name=""):
    """Return the reasons ``password`` is not acceptable; an empty list means it is fine.

    Args:
        password: The candidate password.
        email: The account's email, so it can't be reused in the password.
        name: The account holder's name, for the same reason.
    """
    if len(password) < MIN_LENGTH:
        return [f"Use at least {MIN_LENGTH} characters. A few unrelated words work well."]
    if len(password) > MAX_LENGTH:
        return [f"Use {MAX_LENGTH} characters or fewer."]

    problems = []
    lowered = password.lower()
    # the "core" once digits and symbols tacked onto either end are removed, de-leeted
    core = lowered.strip("0123456789!@#$%^&*()_+-=.,?~ ").translate(_LEET)
    letters = re.sub(r"[^a-z]", "", core)
    if letters in COMMON_WORDS or (not letters and lowered.isdigit()):
        problems.append("That password is too common. Try a few unrelated words instead.")
    elif len(set(lowered)) < 5:
        problems.append("That password is too repetitive.")
    else:
        compact = re.sub(r"[^a-z0-9]", "", lowered)
        if any(compact in sequence for sequence in SEQUENCES):
            problems.append("That password is a predictable sequence.")

    personal = [email.split("@", 1)[0].lower(), *(name or "").lower().split()]
    if any(len(part) >= 4 and part in lowered for part in personal):
        problems.append("Don't include your name or email address.")
    return problems
