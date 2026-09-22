import json
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, redirect, request, session, url_for


bp = Blueprint("localization", __name__)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "mn": "Монгол",
}
TRANSLATIONS_DIR = Path(__file__).parent / "translations"


@lru_cache(maxsize=None)
def _catalog(language):
    if language == "en":
        return {}
    path = TRANSLATIONS_DIR / f"{language}.json"
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def translate(text):
    language = session.get("language", "en")
    return _catalog(language).get(text, text)


@bp.app_context_processor
def add_localization():
    return {
        "t": translate,
        "current_language": session.get("language", "en"),
        "supported_languages": SUPPORTED_LANGUAGES,
    }


@bp.post("/language")
def set_language():
    language = request.form.get("language", "en")
    if language in SUPPORTED_LANGUAGES:
        session["language"] = language
    next_page = request.form.get("next", "")
    if not next_page.startswith("/") or next_page.startswith("//"):
        next_page = url_for("reports.landing")
    return redirect(next_page)
