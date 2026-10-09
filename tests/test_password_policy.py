"""The password policy (NIST SP 800-63B style)."""

import pytest

from runnify.security.passwords import password_problems


@pytest.mark.parametrize(
    "password",
    ["correct horse battery staple", "my dog eats bananas", "Tr4ck-Sp1ts-Fl0w", "x" * 12 + "yz9!"],
)
def test_long_uncommon_passwords_are_accepted(password):
    assert password_problems(password) == []


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short", "at least 12"),
        ("x" * 129, "128 characters or fewer"),
        ("Password2026!", "too common"),
        ("P@ssw0rd12345", "too common"),
        ("123password456", "too common"),
        ("Liverpool2026", "too common"),
        ("123456789012", "too common"),
        ("abcdefghijklm", "sequence"),
        ("qwertyuiopasd", "sequence"),
        ("abababababab", "repetitive"),
    ],
)
def test_weak_passwords_are_rejected_with_a_reason(password, reason):
    problems = password_problems(password)
    assert problems
    assert reason in problems[0]


def test_personal_details_are_rejected():
    problems = password_problems("colm goes running far", email="colm@example.com", name="Colm Ali")
    assert "name or email" in problems[-1]


def test_registration_enforces_the_policy(app, client):
    weak = client.post(
        "/register",
        data={
            "accept_terms": "y",
            "data_consent": "y",
            "name": "A",
            "email": "a@example.com",
            "password": "Password2026!",
        },
    )
    assert b"too common" in weak.data
    ok = client.post(
        "/register",
        data={
            "accept_terms": "y",
            "data_consent": "y",
            "name": "A",
            "email": "a@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert ok.status_code == 302
