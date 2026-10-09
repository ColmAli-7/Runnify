"""Outgoing email.

With no ``MAIL_SERVER`` configured, messages are not sent. In development the
whole message is logged so flows like password reset can be tested locally;
in production only the fact that a message was dropped is logged, because
bodies can contain secrets such as reset links.
"""

import logging

from flask import current_app
from flask_mail import Message

from runnify.extensions import mail

logger = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Send a plain-text email, or log it when mail is not configured.

    Args:
        to: Recipient address.
        subject: Subject line.
        body: Plain-text body.
    """
    config = current_app.config
    if config.get("MAIL_SERVER") or config.get("MAIL_SUPPRESS_SEND"):
        mail.send(Message(subject=subject, recipients=[to], body=body))
        return
    if config["ENV_NAME"] == "development":
        logger.warning(
            "MAIL_SERVER not set; email not sent:\nTo: %s\nSubject: %s\n\n%s", to, subject, body
        )
    else:
        logger.error("MAIL_SERVER not set; dropped email %r", subject)
