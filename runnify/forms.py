"""Forms with server-side validation (Flask-WTF / WTForms).

Every form inherits CSRF protection from ``FlaskForm``. Emails are trimmed and
lower-cased, names trimmed, and every field has an upper length bound so no
input can be arbitrarily large.
"""

import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, Length, Regexp, ValidationError

from runnify.security.passwords import MAX_LENGTH, password_problems

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(value):
    """Trim and lower-case an email address."""
    return (value or "").strip().lower()


def strip(value):
    """Trim surrounding whitespace."""
    return (value or "").strip()


def email_address(form, field):
    """Validate that a field looks like an email address."""
    if not EMAIL_PATTERN.match(field.data or ""):
        raise ValidationError("Enter a valid email address.")


def _email_field(label="Email"):
    return EmailField(
        label,
        filters=[normalise_email],
        validators=[DataRequired("Enter your email address."), Length(max=254), email_address],
    )


def _password_field(label, message):
    return PasswordField(label, validators=[DataRequired(message), Length(max=MAX_LENGTH)])


class LoginForm(FlaskForm):
    """Sign in with email and password."""

    email = _email_field()
    password = _password_field("Password", "Enter your password.")
    remember = BooleanField("Keep me signed in on this device")


class RegisterForm(FlaskForm):
    """Create an account."""

    name = StringField(
        "Name", filters=[strip], validators=[DataRequired("Enter your name."), Length(max=80)]
    )
    email = _email_field()
    password = _password_field("Password", "Choose a password.")

    def validate_password(self, field):
        """Apply the password policy, with the name and email as context."""
        problems = password_problems(field.data, email=self.email.data or "", name=self.name.data)
        if problems:
            raise ValidationError(problems[0])


class ForgotPasswordForm(FlaskForm):
    """Request a password-reset email."""

    email = _email_field()


class ResetPasswordForm(FlaskForm):
    """Choose a new password from a reset link. The policy is applied by the view,
    which knows whose account it is."""

    password = _password_field("New password", "Choose a new password.")
    confirm = PasswordField(
        "Confirm new password", validators=[EqualTo("password", "The passwords don't match.")]
    )


class ChangePasswordForm(FlaskForm):
    """Change password from account settings."""

    password = _password_field("Current password", "Enter your current password.")
    new_password = _password_field("New password", "Choose a new password.")
    confirm_password = PasswordField(
        "Confirm new password", validators=[EqualTo("new_password", "The passwords don't match.")]
    )


class ChangeNameForm(FlaskForm):
    """Change display name from account settings."""

    password = _password_field("Current password", "Enter your current password.")
    new_name = StringField(
        "Name", filters=[strip], validators=[DataRequired("Enter your name."), Length(max=80)]
    )


class GarminConnectForm(FlaskForm):
    """Garmin Connect sign-in, used once to link the account."""

    email = _email_field("Garmin email")
    password = _password_field("Garmin password", "Enter your Garmin password.")


class GarminCodeForm(FlaskForm):
    """Garmin's two-step verification code."""

    code = StringField(
        "Verification code",
        filters=[strip],
        validators=[
            DataRequired("Enter the code Garmin sent you."),
            Regexp(r"^\d{6,8}$", message="Enter the 6-digit code."),
        ],
    )


def _code_field(message="Enter the 6-digit code from your authenticator app."):
    return StringField("Code", filters=[strip], validators=[DataRequired(message), Length(max=20)])


class TwoFactorLoginForm(FlaskForm):
    """Second sign-in step: an authenticator code or a recovery code."""

    code = _code_field()


class TwoFactorEnableForm(FlaskForm):
    """Confirm the authenticator app works, and re-enter the password."""

    code = _code_field()
    password = _password_field("Current password", "Enter your current password.")


class TwoFactorDisableForm(FlaskForm):
    """Turn two-step verification off: password plus a current or recovery code."""

    password = _password_field("Current password", "Enter your current password.")
    code = _code_field("Enter a code from your authenticator app or a recovery code.")


class PasswordConfirmForm(FlaskForm):
    """Re-enter the password before a sensitive action."""

    password = _password_field("Current password", "Enter your current password.")


def first_error(form):
    """Return the first validation message on ``form``, for a flash message."""
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return None
