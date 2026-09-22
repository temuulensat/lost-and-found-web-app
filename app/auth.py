from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)
PASSWORD_HASH_METHOD = "pbkdf2:sha256:600000"


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()


@bp.before_app_request
def enforce_login_gate():
    public_endpoints = {
        "reports.landing",
        "auth.login",
        "auth.signup",
        "localization.set_language",
        "static",
    }
    is_private_upload = request.path.startswith("/static/uploads/")
    if g.user is None and (
        request.endpoint not in public_endpoints or is_private_upload
    ):
        flash("Log in to continue.", "error")
        return redirect(url_for("auth.login"))


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Log in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()

        if not username or not email or not password:
            flash("Complete all fields.", "error")
        elif len(username) > 80 or len(email) > 254 or len(password) > 1024:
            flash("An account field is too long.", "error")
        elif "@" not in email or email.startswith("@") or email.endswith("@") or any(char.isspace() for char in email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone():
            flash("That username or email is already registered.", "error")
        else:
            cursor = db.execute(
                """
                INSERT INTO users (username, email, password_hash, is_admin)
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    generate_password_hash(password, method=PASSWORD_HASH_METHOD),
                    0,
                ),
            )
            db.commit()
            session.clear()
            session["user_id"] = cursor.lastrowid
            flash("Your account has been created.", "success")
            return redirect(url_for("reports.report_item"))

    return render_template("signup.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash("You are now logged in.", "success")
            return redirect(url_for("reports.report_item"))

    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
