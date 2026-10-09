"""HTTP security headers added to every response.

The Content-Security-Policy only allows resources from the site itself: no
inline scripts, no inline style attributes, no third-party hosts. Templates
pass data to scripts through ``<script type="application/json">`` blocks and
scripts set styles through the CSSOM, both of which the policy permits.
"""

from flask import request

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer",
        "camera",
        "geolocation",
        "gyroscope",
        "magnetometer",
        "microphone",
        "payment",
        "usb",
    )
)

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

HSTS = "max-age=31536000; includeSubDomains"


def init_security_headers(app):
    """Register an ``after_request`` hook that adds the security headers.

    ``CSP_REPORT_ONLY`` sends the policy as ``Content-Security-Policy-Report-Only``
    so violations are reported in the browser console without blocking anything.
    """

    @app.after_request
    def add_security_headers(response):
        for name, value in STATIC_HEADERS.items():
            response.headers.setdefault(name, value)

        policy = CONTENT_SECURITY_POLICY
        if app.config["ENV_NAME"] == "production":
            policy += "; upgrade-insecure-requests"
        csp_header = (
            "Content-Security-Policy-Report-Only"
            if app.config.get("CSP_REPORT_ONLY")
            else "Content-Security-Policy"
        )
        response.headers.setdefault(csp_header, policy)

        if request.is_secure and app.config["ENV_NAME"] == "production":
            response.headers.setdefault("Strict-Transport-Security", HSTS)

        # pages can contain personal data: never let a shared browser or proxy cache them
        if request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")
        return response
