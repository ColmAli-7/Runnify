"""Safe redirect targets."""

from urllib.parse import urlsplit


def safe_next_url(target):
    """Return ``target`` if it is a local path on this site, otherwise ``None``.

    Prevents open redirects through ``?next=``: absolute URLs, scheme-relative
    URLs (``//evil.example``) and backslash tricks are all refused.
    """
    if not target:
        return None
    target = target.strip()
    if "\\" in target or not target.startswith("/") or target.startswith("//"):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return target
