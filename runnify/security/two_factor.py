"""Two-step verification: authenticator-app codes (TOTP) and recovery codes.

* Secrets are 160-bit, stored encrypted (``User.totp_secret``).
* A code is accepted for the current 30-second step or one step either side
  (clock drift), and never twice: the last accepted step is remembered, so an
  intercepted code cannot be replayed.
* Recovery codes are random, single-use and stored only as SHA-256 hashes.
  At 40 bits each, and with sign-in attempts rate limited and counted towards
  lockout, they are far beyond online guessing, so a fast hash is appropriate.
* The QR code is drawn on the server as inline SVG; the secret never goes to a
  third-party QR service.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import pyotp
import segno

from runnify.extensions import db
from runnify.models import RecoveryCode, utcnow

ISSUER = "Runnify"
RECOVERY_CODE_COUNT = 10
VALID_WINDOW = 1  # steps either side of now


def new_secret():
    """Return a fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret, email):
    """The ``otpauth://`` URI an authenticator app scans."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(uri):
    """Return the URI as an inline SVG QR code."""
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, omitsize=True)


def format_secret(secret):
    """Group a secret in fours for typing it in by hand."""
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


def _normalise(code):
    return "".join(ch for ch in (code or "") if ch.isalnum()).lower()


def accept_code(user, code, secret=None):
    """Check an authenticator code for ``user`` and record it so it can't be reused.

    Args:
        user: The account (its ``totp_last_step`` is updated on success).
        code: The 6-digit code the user typed.
        secret: Check against this secret instead of the stored one (used while
            setting up, before the secret is saved).

    Returns:
        ``True`` if the code is valid and hasn't been used before.
    """
    secret = secret or user.totp_secret
    code = _normalise(code)
    if not secret or len(code) != 6 or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    # must be timezone-aware: pyotp reads naive times as local
    now_step = totp.timecode(datetime.now(UTC))
    for step in range(now_step - VALID_WINDOW, now_step + VALID_WINDOW + 1):
        if user.totp_last_step is not None and step <= user.totp_last_step:
            continue  # this code (or an earlier one) was already used
        if hmac.compare_digest(totp.generate_otp(step), code):
            user.totp_last_step = step
            return True
    return False


def _hash_recovery_code(code):
    return hashlib.sha256(_normalise(code).encode()).hexdigest()


def new_recovery_codes():
    """Return ``(codes, hashes)``: codes to show the user once, hashes to store."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(5)  # 40 random bits, shown as two groups of five
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_hash_recovery_code(code) for code in codes]


def recovery_code_hash(code):
    """Hash a recovery code the user typed, for lookup."""
    return _hash_recovery_code(code)


def replace_recovery_codes(user):
    """Discard ``user``'s recovery codes and issue new ones; returns the codes to show once."""
    RecoveryCode.query.filter_by(user_id=user.id).delete()
    codes, hashes = new_recovery_codes()
    db.session.add_all(RecoveryCode(user_id=user.id, code_hash=h) for h in hashes)
    return codes


def use_recovery_code(user, code):
    """Spend one of ``user``'s unused recovery codes; returns ``True`` if it was valid."""
    record = RecoveryCode.query.filter_by(
        user_id=user.id, code_hash=recovery_code_hash(code), used_at=None
    ).first()
    if record is None:
        return False
    record.used_at = utcnow()
    return True


def remaining_recovery_codes(user):
    """How many unused recovery codes ``user`` has."""
    return RecoveryCode.query.filter_by(user_id=user.id, used_at=None).count()


def enable(user, secret):
    """Turn on two-step verification with a confirmed ``secret``; returns new recovery codes."""
    user.totp_secret = secret
    user.totp_enabled_at = utcnow()
    return replace_recovery_codes(user)


def disable(user):
    """Turn off two-step verification and delete the recovery codes."""
    user.totp_secret = user.totp_enabled_at = user.totp_last_step = None
    RecoveryCode.query.filter_by(user_id=user.id).delete()
