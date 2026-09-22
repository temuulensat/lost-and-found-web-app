"""Session-bound CSRF protection for browser forms."""

import hmac
import secrets

from flask import abort, request, session


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def init_app(app):
    @app.before_request
    def check_csrf():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                abort(400, description="Invalid CSRF token.")

    @app.context_processor
    def expose_csrf():
        return {"csrf_token": csrf_token}
