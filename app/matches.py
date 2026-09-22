from flask import Blueprint, abort, flash, g, redirect, render_template, url_for

from .auth import login_required
from .db import get_db
from .matching import POSSIBLE_MATCH_THRESHOLD, score_match

bp = Blueprint("matches", __name__)

STATUS_LABEL_SQL = """
    CASE COALESCE(claim.status, 'possible')
        WHEN 'claim_pending' THEN 'Claim Pending'
        WHEN 'confirmed' THEN 'Confirmed'
        WHEN 'returned' THEN 'Returned'
        ELSE 'Possible Match'
    END
"""

MATCH_SELECT_SQL = """
    SELECT lost.id AS lost_item_id, lost.user_id AS lost_user_id,
           lost.item_name AS lost_item_name, lost.category AS lost_category,
           lost.color AS lost_color, lost.location AS lost_location,
           lost.country AS lost_country, lost.region AS lost_region,
           lost.city AS lost_city, lost.area AS lost_area,
           lost.date AS lost_date, lost.description AS lost_description,
           lost.image_filename AS lost_image_filename,
           found.id AS found_item_id, found.user_id AS found_user_id,
           found.item_name AS found_item_name, found.category AS found_category,
           found.color AS found_color, found.location AS found_location,
           found.country AS found_country, found.region AS found_region,
           found.city AS found_city, found.area AS found_area,
           found.date AS found_date, found.description AS found_description,
           found.image_filename AS found_image_filename,
           {status_label} AS match_status,
           claim.status AS claim_status, claim.claimant_id, claim.claim_round,
           CASE WHEN lost.user_id = ?
                THEN 'Possible match found for your lost item.'
                ELSE 'Your found item may match someone’s lost item.'
           END AS notification_message,
           CASE WHEN view.seen_at IS NULL THEN 1 ELSE 0 END AS is_new
    FROM items AS lost
    JOIN items AS found
      ON found.report_type = 'found'
     AND found.user_id IS NOT NULL
     AND found.user_id != lost.user_id
    LEFT JOIN match_claims AS claim
      ON claim.lost_item_id = lost.id AND claim.found_item_id = found.id
    LEFT JOIN match_views AS view
      ON view.user_id = ?
     AND view.lost_item_id = lost.id
     AND view.found_item_id = found.id
    WHERE lost.report_type = 'lost'
      AND lost.status = 'open'
      AND found.status = 'open'
      AND (lost.user_id = ? OR found.user_id = ?)
""".format(status_label=STATUS_LABEL_SQL)


def _lost_from_match(row):
    return {
        "item_name": row["lost_item_name"],
        "category": row["lost_category"],
        "color": row["lost_color"],
        "location": row["lost_location"],
        "country": row["lost_country"],
        "region": row["lost_region"],
        "city": row["lost_city"],
        "area": row["lost_area"],
        "date": row["lost_date"],
        "description": row["lost_description"],
    }


def _found_from_match(row):
    return {
        "item_name": row["found_item_name"],
        "category": row["found_category"],
        "color": row["found_color"],
        "location": row["found_location"],
        "country": row["found_country"],
        "region": row["found_region"],
        "city": row["found_city"],
        "area": row["found_area"],
        "date": row["found_date"],
        "description": row["found_description"],
    }


def _score_match_row(row):
    scored = dict(row)
    scored.update(score_match(_lost_from_match(row), _found_from_match(row)))
    return scored


def _is_visible_match(row):
    scored = _score_match_row(row)
    if scored["match_score"] >= POSSIBLE_MATCH_THRESHOLD or scored["claim_status"] is not None:
        return scored
    return None


def _user_match_rows(db):
    rows = db.execute(
        MATCH_SELECT_SQL,
        (g.user["id"], g.user["id"], g.user["id"], g.user["id"]),
    ).fetchall()
    matches = []
    for row in rows:
        scored = _is_visible_match(row)
        if scored is not None:
            matches.append(scored)
    matches.sort(
        key=lambda item: (
            not item["is_new"],
            -item["match_score"],
            -item["found_item_id"],
        )
    )
    return matches


def get_match_for_user(lost_item_id, found_item_id):
    match = get_db().execute(
        """
        SELECT lost.id AS lost_item_id, lost.user_id AS lost_user_id,
               lost.item_name AS lost_item_name, lost.category AS lost_category,
               lost.color AS lost_color, lost.location AS lost_location,
               lost.country AS lost_country, lost.region AS lost_region,
               lost.city AS lost_city, lost.area AS lost_area,
               lost.date AS lost_date, lost.description AS lost_description,
               found.id AS found_item_id, found.user_id AS found_user_id,
               found.item_name AS found_item_name, found.category AS found_category,
               found.color AS found_color, found.location AS found_location,
               found.country AS found_country, found.region AS found_region,
               found.city AS found_city, found.area AS found_area,
               found.date AS found_date, found.description AS found_description,
               claim.status, claim.status AS claim_status,
               claim.claimant_id, claim.claim_round
        FROM items AS lost
        JOIN items AS found ON found.id = ?
        LEFT JOIN match_claims AS claim
          ON claim.lost_item_id = lost.id AND claim.found_item_id = found.id
        WHERE lost.id = ?
          AND lost.report_type = 'lost'
          AND found.report_type = 'found'
          AND lost.status = 'open'
          AND found.status = 'open'
          AND lost.user_id IS NOT NULL
          AND found.user_id IS NOT NULL
          AND lost.user_id != found.user_id
          AND (lost.user_id = ? OR found.user_id = ?)
        """,
        (
            found_item_id,
            lost_item_id,
            g.user["id"],
            g.user["id"],
        ),
    ).fetchone()
    if match is None or _is_visible_match(match) is None:
        abort(404)
    return match


def other_user_id(match):
    if g.user["id"] == match["lost_user_id"]:
        return match["found_user_id"]
    return match["lost_user_id"]


def notify(db, user_id, lost_item_id, found_item_id, event_type, claim_round, message):
    db.execute(
        """
        INSERT OR IGNORE INTO match_status_notifications
            (user_id, lost_item_id, found_item_id, event_type, claim_round, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, lost_item_id, found_item_id, event_type, claim_round, message),
    )


@bp.app_context_processor
def add_unseen_match_count():
    if g.get("user") is None:
        return {"unseen_match_count": 0}

    db = get_db()
    match_count = sum(1 for match in _user_match_rows(db) if match["is_new"])
    event_count = db.execute(
        "SELECT COUNT(*) FROM match_status_notifications WHERE user_id = ? AND seen_at IS NULL",
        (g.user["id"],),
    ).fetchone()[0]
    return {"unseen_match_count": match_count + event_count}


@bp.post("/matches/<int:lost_item_id>/<int:found_item_id>/claim")
@login_required
def claim_match(lost_item_id, found_item_id):
    db = get_db()
    match = get_match_for_user(lost_item_id, found_item_id)
    db.execute(
        """
        INSERT OR IGNORE INTO match_claims (lost_item_id, found_item_id)
        VALUES (?, ?)
        """,
        (lost_item_id, found_item_id),
    )
    updated = db.execute(
        """
        UPDATE match_claims
        SET status = 'claim_pending', claimant_id = ?,
            claim_round = claim_round + 1, updated_at = CURRENT_TIMESTAMP
        WHERE lost_item_id = ? AND found_item_id = ? AND status = 'possible'
        """,
        (g.user["id"], lost_item_id, found_item_id),
    )
    if updated.rowcount != 1:
        db.rollback()
        abort(409)
    claim_round = db.execute(
        "SELECT claim_round FROM match_claims WHERE lost_item_id = ? AND found_item_id = ?",
        (lost_item_id, found_item_id),
    ).fetchone()[0]
    notify(
        db,
        other_user_id(match),
        lost_item_id,
        found_item_id,
        "claim_pending",
        claim_round,
        "A match claim needs your response.",
    )
    db.commit()
    flash("The claim has been sent for review.", "success")
    return redirect(url_for("matches.match_list"))


@bp.post("/matches/<int:lost_item_id>/<int:found_item_id>/<decision>")
@login_required
def respond_to_claim(lost_item_id, found_item_id, decision):
    if decision not in {"accept", "reject"}:
        abort(404)
    db = get_db()
    match = get_match_for_user(lost_item_id, found_item_id)
    if match["status"] != "claim_pending" or match["claimant_id"] == g.user["id"]:
        abort(403)

    if decision == "accept":
        status = "confirmed"
        event_type = "accepted"
        message = "Your match claim was accepted."
    else:
        status = "possible"
        event_type = "rejected"
        message = "Your match claim was rejected."

    db.execute(
        """
        UPDATE match_claims
        SET status = ?, claimant_id = CASE WHEN ? = 'possible' THEN NULL ELSE claimant_id END,
            updated_at = CURRENT_TIMESTAMP
        WHERE lost_item_id = ? AND found_item_id = ? AND status = 'claim_pending'
        """,
        (status, status, lost_item_id, found_item_id),
    )
    notify(
        db,
        match["claimant_id"],
        lost_item_id,
        found_item_id,
        event_type,
        match["claim_round"],
        message,
    )
    db.commit()
    flash(f"The claim has been {event_type}.", "success")
    return redirect(url_for("matches.match_list"))


@bp.post("/matches/<int:lost_item_id>/<int:found_item_id>/returned")
@login_required
def mark_returned(lost_item_id, found_item_id):
    db = get_db()
    match = get_match_for_user(lost_item_id, found_item_id)
    if match["status"] != "confirmed":
        abort(409)

    db.execute(
        """
        UPDATE match_claims SET status = 'returned', updated_at = CURRENT_TIMESTAMP
        WHERE lost_item_id = ? AND found_item_id = ? AND status = 'confirmed'
        """,
        (lost_item_id, found_item_id),
    )
    db.execute(
        "UPDATE items SET status = 'closed' WHERE id IN (?, ?)",
        (lost_item_id, found_item_id),
    )
    notify(
        db,
        other_user_id(match),
        lost_item_id,
        found_item_id,
        "returned",
        match["claim_round"],
        "The matched item was marked as returned.",
    )
    db.commit()
    flash("The item has been marked returned and both reports are closed.", "success")
    return redirect(url_for("matches.match_list"))


@bp.route("/matches")
@login_required
def match_list():
    db = get_db()
    matches = _user_match_rows(db)

    notifications = db.execute(
        """
        SELECT message, created_at
        FROM match_status_notifications
        WHERE user_id = ? AND seen_at IS NULL
        ORDER BY id DESC
        """,
        (g.user["id"],),
    ).fetchall()

    db.executemany(
        """
        INSERT OR IGNORE INTO match_views (user_id, lost_item_id, found_item_id)
        VALUES (?, ?, ?)
        """,
        [(g.user["id"], match["lost_item_id"], match["found_item_id"]) for match in matches],
    )
    db.execute(
        """
        UPDATE match_status_notifications
        SET seen_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND seen_at IS NULL
        """,
        (g.user["id"],),
    )
    db.commit()

    return render_template("matches.html", matches=matches, notifications=notifications)
