from pathlib import Path
import os

from flask import Flask

from .csrf import init_app as init_csrf


def create_app(test_config=None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    data_dir = Path(os.environ.get("APP_DATA_DIR", app.instance_path))
    trusted_hosts = os.environ.get("APP_TRUSTED_HOSTS")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=data_dir / "lost_and_found.sqlite",
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        UPLOAD_FOLDER=data_dir / "uploads",
        TRUSTED_HOSTS=trusted_hosts.split(",") if trusted_hosts else None,
        SESSION_COOKIE_SECURE=os.environ.get("APP_COOKIE_SECURE", "1") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config is not None:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or (
        not app.config.get("TESTING") and len(app.config["SECRET_KEY"]) < 32
    ):
        raise RuntimeError("SECRET_KEY must be a persistent random value of at least 32 characters.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from . import auth, db, localization, matches, messaging
    from .routes import bp

    db.init_app(app)
    init_csrf(app)
    app.register_blueprint(localization.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(matches.bp)
    app.register_blueprint(messaging.bp)
    app.register_blueprint(bp)

    with app.app_context():
        db.init_db()

    return app
