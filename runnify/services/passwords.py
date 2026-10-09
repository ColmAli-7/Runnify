"""Input validation helpers."""


def passw_strength(password):
    """Check that a password meets Runnify's strength rules.

    A strong password is at least 8 characters long and contains a letter,
    a digit and a special character.

    Args:
        password: The candidate password.

    Returns:
        ``[True]`` if the password is strong, otherwise
        ``[False, (message, flash_category)]`` describing the first rule that
        failed, ready to pass to ``flask.flash``.
    """
    if len(password) < 8:
        return [False, ("Password must be 8 characters or greater.", "error")]
    if not any(x.isalpha() for x in password):  # a letter
        return [False, ("Password must contain a letter.", "error")]
    if not any(x.isdigit() for x in password):  # number
        return [False, ("Password must contain a number.", "error")]
    if not any((x in """!@#$%^&*()_+{}[]\\|:;"'<,>.?/""") for x in password):  # special char
        return [
            False,
            (
                """Password must contain a special letter: !@#$%^&*()_+{}[]\\|:;"'<,>.?/""",
                "error",
            ),
        ]
    return [True]  # strong password
