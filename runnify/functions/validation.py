def passw_strength(password):
    # checks password strength and returns a flag and message if weak
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
