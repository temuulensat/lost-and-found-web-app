from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .matching import POSSIBLE_MATCH_THRESHOLD, score_match

bp = Blueprint("messaging", __name__)


@bp.app_context_processor
def add_unread_message_count():
    if g.get("user") is None:
        return {"unread_message_count": 0}

    row = get_db().execute(
        """
        SELECT COUNT(*)
        FROM messages AS message
        JOIN conversations AS conversation
          ON conversation.id = message.conversation_id
        LEFT JOIN conversation_reads AS reading
          ON reading.conversation_id = conversation.id AND reading.user_id = ?
        WHERE (conversation.lost_user_id = ? OR conversation.found_user_id = ?)
          AND message.sender_id != ?
          AND message.id > COALESCE(reading.last_read_message_id, 0)
        """,
        (g.user["id"], g.user["id"], g.user["id"], g.user["id"]),
    ).fetchone()
    return {"unread_message_count": row[0]}


def get_conversation_for_user(conversation_id):
    conversation = get_db().execute(
        """
        SELECT c.*, lost.item_name AS lost_item_name,
               found.item_name AS found_item_name,
               lost_user.username AS lost_username,
               found_user.username AS found_username
        FROM conversations AS c
        JOIN items AS lost ON lost.id = c.lost_item_id
        JOIN items AS found ON found.id = c.found_item_id
        JOIN users AS lost_user ON lost_user.id = c.lost_user_id
        JOIN users AS found_user ON found_user.id = c.found_user_id
        WHERE c.id = ? AND (c.lost_user_id = ? OR c.found_user_id = ?)
        """,
        (conversation_id, g.user["id"], g.user["id"]),
    ).fetchone()
    if conversation is None:
        abort(404)
    return conversation


@bp.post("/items/<int:lost_item_id>/matches/<int:found_item_id>/message")
@login_required
def start_conversation(lost_item_id, found_item_id):
    db = get_db()
    match = db.execute(
        """
        SELECT lost.user_id AS lost_user_id, found.user_id AS found_user_id,
               lost.item_name AS lost_item_name, lost.category AS lost_category,
               lost.color AS lost_color, lost.location AS lost_location,
               lost.country AS lost_country, lost.region AS lost_region,
               lost.city AS lost_city, lost.area AS lost_area,
               lost.date AS lost_date, lost.description AS lost_description,
               found.item_name AS found_item_name, found.category AS found_category,
               found.color AS found_color, found.location AS found_location,
               found.country AS found_country, found.region AS found_region,
               found.city AS found_city, found.area AS found_area,
               found.date AS found_date, found.description AS found_description
        FROM items AS lost
        JOIN items AS found ON found.id = ?
        WHERE lost.id = ?
          AND lost.report_type = 'lost'
          AND found.report_type = 'found'
          AND lost.status = 'open'
          AND found.status = 'open'
          AND lost.user_id IS NOT NULL
          AND found.user_id IS NOT NULL
          AND found.user_id != lost.user_id
          AND (lost.user_id = ? OR found.user_id = ?)
        """,
        (
            found_item_id,
            lost_item_id,
            g.user["id"],
            g.user["id"],
        ),
    ).fetchone()
    if match is None:
        abort(404)
    score = score_match(
        {
            "item_name": match["lost_item_name"],
            "category": match["lost_category"],
            "color": match["lost_color"],
            "location": match["lost_location"],
            "country": match["lost_country"],
            "region": match["lost_region"],
            "city": match["lost_city"],
            "area": match["lost_area"],
            "date": match["lost_date"],
            "description": match["lost_description"],
        },
        {
            "item_name": match["found_item_name"],
            "category": match["found_category"],
            "color": match["found_color"],
            "location": match["found_location"],
            "country": match["found_country"],
            "region": match["found_region"],
            "city": match["found_city"],
            "area": match["found_area"],
            "date": match["found_date"],
            "description": match["found_description"],
        },
    )
    if score["match_score"] < POSSIBLE_MATCH_THRESHOLD:
        abort(404)

    db.execute(
        """
        INSERT OR IGNORE INTO conversations
            (lost_item_id, found_item_id, lost_user_id, found_user_id)
        VALUES (?, ?, ?, ?)
        """,
        (lost_item_id, found_item_id, match["lost_user_id"], match["found_user_id"]),
    )
    db.commit()
    conversation = db.execute(
        "SELECT id FROM conversations WHERE lost_item_id = ? AND found_item_id = ?",
        (lost_item_id, found_item_id),
    ).fetchone()
    db.executemany(
        """
        INSERT OR IGNORE INTO conversation_reads
            (conversation_id, user_id, last_read_message_id)
        VALUES (?, ?, 0)
        """,
        (
            (conversation["id"], match["lost_user_id"]),
            (conversation["id"], match["found_user_id"]),
        ),
    )
    db.commit()
    return redirect(url_for("messaging.conversation", conversation_id=conversation["id"]))


@bp.route("/conversations")
@login_required
def conversations():
    rows = get_db().execute(
        """
        SELECT c.id, c.created_at, lost.item_name AS lost_item_name,
               found.item_name AS found_item_name,
               CASE WHEN c.lost_user_id = ?
                    THEN found_user.username ELSE lost_user.username END AS other_username,
               (SELECT COUNT(*) FROM messages AS unread
                WHERE unread.conversation_id = c.id
                  AND unread.sender_id != ?
                  AND unread.id > COALESCE(
                      (SELECT last_read_message_id FROM conversation_reads
                       WHERE conversation_id = c.id AND user_id = ?), 0
                  )) AS unread_count,
               (SELECT body FROM messages WHERE conversation_id = c.id
                ORDER BY id DESC LIMIT 1) AS last_message,
               COALESCE((SELECT created_at FROM messages WHERE conversation_id = c.id
                         ORDER BY id DESC LIMIT 1), c.created_at) AS last_activity
        FROM conversations AS c
        JOIN items AS lost ON lost.id = c.lost_item_id
        JOIN items AS found ON found.id = c.found_item_id
        JOIN users AS lost_user ON lost_user.id = c.lost_user_id
        JOIN users AS found_user ON found_user.id = c.found_user_id
        WHERE c.lost_user_id = ? OR c.found_user_id = ?
        ORDER BY last_activity DESC, c.id DESC
        """,
        (
            g.user["id"],
            g.user["id"],
            g.user["id"],
            g.user["id"],
            g.user["id"],
        ),
    ).fetchall()
    return render_template("conversations.html", conversations=rows)


@bp.route("/conversations/<int:conversation_id>", methods=("GET", "POST"))
@login_required
def conversation(conversation_id):
    conversation_row = get_conversation_for_user(conversation_id)
    db = get_db()

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Enter a message before sending.", "error")
        elif len(body) > 2000:
            flash("Messages must be 2,000 characters or fewer.", "error")
        else:
            db.execute(
                "INSERT INTO messages (conversation_id, sender_id, body) VALUES (?, ?, ?)",
                (conversation_id, g.user["id"], body),
            )
            db.commit()
            return redirect(
                url_for("messaging.conversation", conversation_id=conversation_id)
            )

    messages = db.execute(
        """
        SELECT m.id, m.body, m.created_at, m.sender_id, u.username
        FROM messages AS m
        JOIN users AS u ON u.id = m.sender_id
        WHERE m.conversation_id = ?
        ORDER BY m.id
        """,
        (conversation_id,),
    ).fetchall()
    last_message_id = messages[-1]["id"] if messages else 0
    db.execute(
        """
        INSERT INTO conversation_reads
            (conversation_id, user_id, last_read_message_id, read_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(conversation_id, user_id) DO UPDATE SET
            last_read_message_id = excluded.last_read_message_id,
            read_at = CURRENT_TIMESTAMP
        """,
        (conversation_id, g.user["id"], last_message_id),
    )
    db.commit()
    return render_template(
        "conversation.html", conversation=conversation_row, messages=messages
    )
