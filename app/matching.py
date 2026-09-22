from datetime import date
from difflib import SequenceMatcher
import re


POSSIBLE_MATCH_THRESHOLD = 60


def _value(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _normalize(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokens(value):
    return set(re.findall(r"[a-z0-9]+", _normalize(value)))


def _text_similarity(left, right):
    left_text = _normalize(left)
    right_text = _normalize(right)
    if not left_text or not right_text:
        return 0.0

    sequence_score = SequenceMatcher(None, left_text, right_text).ratio()
    left_tokens = _tokens(left_text)
    right_tokens = _tokens(right_text)
    token_score = 0.0
    if left_tokens and right_tokens:
        token_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(sequence_score, token_score)


def _date_distance(left, right):
    try:
        left_date = date.fromisoformat(left)
        right_date = date.fromisoformat(right)
    except (TypeError, ValueError):
        return None
    return abs((left_date - right_date).days)


def _date_score(days):
    if days is None:
        return 0
    if days == 0:
        return 10
    if days == 1:
        return 9
    if days <= 3:
        return 7
    if days <= 7:
        return 5
    if days <= 14:
        return 3
    return 0


def _reason(key, **values):
    return {"key": key, "values": values}


def score_match(lost, found):
    """Return a deterministic 0-100 match score and short reason list."""
    score = 0
    category_reason = None
    color_reason = None
    location_reason = None
    date_reason = None
    name_reason = None
    description_reason = None

    name_similarity = _text_similarity(_value(lost, "item_name"), _value(found, "item_name"))
    name_score = round(name_similarity * 25)
    score += name_score
    if name_similarity >= 0.85:
        name_reason = _reason("Very similar item name")
    elif name_similarity >= 0.55:
        name_reason = _reason("Similar item name")

    if _normalize(_value(lost, "category")) == _normalize(_value(found, "category")):
        score += 20
        category_reason = _reason("Same category")

    color_similarity = _text_similarity(_value(lost, "color"), _value(found, "color"))
    color_score = round(color_similarity * 15)
    score += color_score
    if color_similarity >= 0.95:
        color_reason = _reason("Same color")
    elif color_similarity >= 0.6:
        color_reason = _reason("Similar color")

    location_score = 0
    if _normalize(_value(lost, "country")) and _normalize(_value(lost, "country")) == _normalize(_value(found, "country")):
        location_score += 4
        location_reason = "Same country"
        if _normalize(_value(lost, "region")) and _normalize(_value(lost, "region")) == _normalize(_value(found, "region")):
            location_score += 4
            location_reason = "Same region"
        if _normalize(_value(lost, "city")) and _normalize(_value(lost, "city")) == _normalize(_value(found, "city")):
            location_score += 8
            location_reason = "Same city"
        if _normalize(_value(lost, "area")) and _normalize(_value(lost, "area")) == _normalize(_value(found, "area")):
            location_score += 4
            if location_reason == "Same city":
                location_reason = "Same area"
        location_reason = _reason(location_reason)
    else:
        location_similarity = _text_similarity(_value(lost, "location"), _value(found, "location"))
        location_score = round(location_similarity * 20)
        if location_similarity >= 0.65:
            location_reason = _reason("Similar location")
    score += min(location_score, 20)

    days = _date_distance(_value(lost, "date"), _value(found, "date"))
    score += _date_score(days)
    if days == 0:
        date_reason = _reason("Reported same day")
    elif days == 1:
        date_reason = _reason("Reported 1 day apart")
    elif days is not None and days <= 14:
        date_reason = _reason("Reported {days} days apart", days=days)

    description_similarity = _text_similarity(
        _value(lost, "description"), _value(found, "description")
    )
    score += round(description_similarity * 10)
    if description_similarity >= 0.5:
        description_reason = _reason("Similar description")

    reasons = [
        reason
        for reason in (
            category_reason,
            color_reason,
            location_reason,
            date_reason,
            name_reason,
            description_reason,
        )
        if reason is not None
    ]

    return {
        "match_score": max(0, min(100, round(score))),
        "match_reasons": reasons,
    }
