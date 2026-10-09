"""Security headers are present on every response."""

from runnify import create_app
from runnify.security.headers import CONTENT_SECURITY_POLICY
from tests.test_config import SafeProductionConfig


def test_baseline_headers(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cache-Control"] == "no-store"


def test_csp_allows_only_the_site_itself(client):
    headers = client.get("/").headers
    policy = headers.get("Content-Security-Policy") or headers["Content-Security-Policy-Report-Only"]
    assert policy.startswith(CONTENT_SECURITY_POLICY)
    assert "'unsafe-inline'" not in policy
    assert "frame-ancestors 'none'" in policy


def test_hsts_only_over_https_in_production():
    client = create_app(SafeProductionConfig).test_client()
    plain = client.get("/", base_url="http://runnify.example.com")
    assert "Strict-Transport-Security" not in plain.headers
    secure = client.get("/", base_url="https://runnify.example.com")
    assert secure.headers["Strict-Transport-Security"].startswith("max-age=31536000")
