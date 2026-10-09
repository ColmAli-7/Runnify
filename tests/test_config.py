"""Configuration profiles and production safety checks."""

import pytest

from runnify import create_app
from runnify.config import (
    DevelopmentConfig,
    ProductionConfig,
    TestConfig,
    database_url,
    get_config,
    validate_production_config,
)

STRONG_KEY = "k" * 48
FERNET_KEY = TestConfig.FERNET_KEY


class SafeProductionConfig(ProductionConfig):
    SECRET_KEY = STRONG_KEY
    FERNET_KEY = FERNET_KEY
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://user:pw@db.example.com/runnify"
    PUBLIC_BASE_URL = "https://runnify.example.com"
    TRUSTED_HOSTS = ["runnify.example.com"]


def test_app_env_selects_the_profile(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert get_config() is ProductionConfig
    monkeypatch.delenv("APP_ENV")
    assert get_config() is DevelopmentConfig
    with pytest.raises(RuntimeError):
        get_config("staging")


@pytest.mark.parametrize("url", ["postgres://u:p@host/db", "postgresql://u:p@host/db"])
def test_postgres_urls_use_the_installed_psycopg2_driver(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert database_url() == "postgresql+psycopg2://u:p@host/db"


def test_safe_production_config_has_no_problems():
    config = {k: getattr(SafeProductionConfig, k) for k in dir(SafeProductionConfig) if k.isupper()}
    assert validate_production_config(config) == []


def test_production_refuses_to_start_with_unsafe_settings():
    class UnsafeConfig(ProductionConfig):
        SECRET_KEY = "short"
        FERNET_KEY = None
        SQLALCHEMY_DATABASE_URI = "sqlite://"
        PUBLIC_BASE_URL = "http://insecure.example.com"
        TRUSTED_HOSTS = None

    with pytest.raises(RuntimeError) as excinfo:
        create_app(UnsafeConfig)
    message = str(excinfo.value)
    for setting in ("SECRET_KEY", "FERNET_KEY", "DATABASE_URL", "PUBLIC_BASE_URL", "ALLOWED_HOSTS"):
        assert setting in message


def test_production_cookies_are_secure():
    app = create_app(SafeProductionConfig)
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_untrusted_host_header_is_rejected():
    app = create_app(SafeProductionConfig)
    client = app.test_client()
    assert client.get("/", headers={"Host": "evil.example.net"}).status_code == 400


def test_proxy_headers_are_trusted_only_in_production():
    seen = {}
    app = create_app(SafeProductionConfig)

    @app.get("/_probe")
    def probe():
        from flask import request

        seen["ip"], seen["scheme"] = request.remote_addr, request.scheme
        return ""

    app.test_client().get(
        "/_probe",
        headers={
            "Host": "runnify.example.com",
            "X-Forwarded-For": "203.0.113.7",
            "X-Forwarded-Proto": "https",
        },
    )
    assert seen == {"ip": "203.0.113.7", "scheme": "https"}
