from datetime import date as calendar_date

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from .auth import login_required
from .db import get_db
from .matching import POSSIBLE_MATCH_THRESHOLD, score_match
from .location_data import (
    FALLBACK_OPTION,
    OTHER_AREA,
    areas,
    is_valid_location,
    location_options_cities,
    location_options_country,
    location_options_regions,
)
from .localization import translate
from .uploads import delete_image, save_image

bp = Blueprint("reports", __name__)
MAJOR_MATCH_FIELDS = (
    "report_type",
    "item_name",
    "category",
    "color",
    "location",
    "date",
)


def validate_report_fields(item_name, category, color, date, description):
    categories = {"Electronics", "Bags", "Wallets", "Keys", "Clothing", "Jewelry", "Documents/IDs", "School items", "Other"}
    colors = {"Black", "White", "Gray", "Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Pink", "Brown", "Gold", "Silver", "Multicolor", "Other"}
    if category not in categories or (color and color not in colors):
        return "Choose a valid category and color."
    if len(item_name) > 200 or len(description) > 5000:
        return "Item name or description is too long."
    try:
        calendar_date.fromisoformat(date)
    except ValueError:
        return "Enter a valid date."
    return None


def compose_location(area, city, region, country):
    return f"{area}, {city}, {region}, {country}"


def translated_location_options(options):
    translated = []
    for option in options:
        if isinstance(option, str):
            translated.append({"name": translate(option), "value": option, "code": option})
        elif option["name"] in {FALLBACK_OPTION, OTHER_AREA}:
            item = dict(option)
            item["value"] = option["name"]
            item["name"] = translate(option["name"])
            translated.append(item)
        else:
            translated.append(option)
    return translated


def invalidate_match_state_for_item(db, item_id, preserve_conversations=False):
    if not preserve_conversations:
        db.execute(
            """
            DELETE FROM messages
            WHERE conversation_id IN (
                SELECT id FROM conversations
                WHERE lost_item_id = ? OR found_item_id = ?
            )
            """,
            (item_id, item_id),
        )
        db.execute(
            "DELETE FROM conversations WHERE lost_item_id = ? OR found_item_id = ?",
            (item_id, item_id),
        )
    db.execute(
        """
        DELETE FROM match_status_notifications
        WHERE lost_item_id = ? OR found_item_id = ?
        """,
        (item_id, item_id),
    )
    db.execute(
        "DELETE FROM match_claims WHERE lost_item_id = ? OR found_item_id = ?",
        (item_id, item_id),
    )
    db.execute(
        "DELETE FROM match_views WHERE lost_item_id = ? OR found_item_id = ?",
        (item_id, item_id),
    )


@bp.get("/")
def landing():
    if g.user is not None:
        return redirect(url_for("reports.report_item"))
    return render_template("landing.html")


@bp.get("/report-photos/<path:filename>")
def report_photo(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.get("/locations/regions")
def location_regions():
    return jsonify(
        translated_location_options(location_options_regions(request.args.get("country", "")))
    )


@bp.get("/locations/cities")
def location_cities():
    return jsonify(
        translated_location_options(
            location_options_cities(
                request.args.get("country", ""), request.args.get("region", "")
            )
        )
    )


@bp.get("/locations/areas")
def location_areas():
    return jsonify(
        translated_location_options(
            areas(
                request.args.get("country", ""),
                request.args.get("region", ""),
                request.args.get("city", ""),
            )
        )
    )


@bp.post("/items/<int:item_id>/delete")
@login_required
def delete_item(item_id):
    db = get_db()
    item = db.execute(
        "SELECT id, image_filename FROM items WHERE id = ? AND user_id = ?",
        (item_id, g.user["id"]),
    ).fetchone()
    if item is None:
        abort(404)

    invalidate_match_state_for_item(db, item_id)
    db.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,),
    )
    db.commit()
    delete_image(item["image_filename"])
    flash("Your report has been deleted.", "success")
    return redirect(url_for("reports.my_reports"))


@bp.route("/items/<int:item_id>/edit", methods=("GET", "POST"))
@login_required
def edit_item(item_id):
    db = get_db()
    item = db.execute(
        "SELECT * FROM items WHERE id = ? AND user_id = ?",
        (item_id, g.user["id"]),
    ).fetchone()
    if item is None:
        abort(404)

    if request.method == "POST":
        report_type = request.form.get("report_type", "").strip()
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "").strip()
        color = request.form.get("color", "").strip()
        country = request.form.get("country", "").strip()
        region = request.form.get("region", "").strip()
        city = request.form.get("city", "").strip()
        area = request.form.get("area", "").strip()
        date = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "").strip()
        location = compose_location(area, city, region, country)

        if report_type not in {"lost", "found"}:
            flash("Choose whether the item was lost or found.", "error")
        elif status not in {"open", "resolved", "closed"}:
            flash("Choose a valid report status.", "error")
        elif not all((item_name, category, date)):
            flash("Complete all required fields.", "error")
        elif validation_error := validate_report_fields(item_name, category, color, date, description):
            flash(validation_error, "error")
        elif not is_valid_location(country, region, city, area):
            flash("Choose a valid country, region, city, and area.", "error")
        else:
            try:
                new_image = save_image(request.files.get("photo"))
            except ValueError as error:
                flash(str(error), "error")
                return render_template(
                    "edit_item.html", item=item, countries=location_options_country()
                )

            image_filename = item["image_filename"]
            if new_image:
                image_filename = new_image
            elif request.form.get("remove_photo") == "yes":
                image_filename = None

            major_changed = any(
                (item[field] or "") != (value or "")
                for field, value in {
                    "report_type": report_type,
                    "item_name": item_name,
                    "category": category,
                    "color": color,
                    "location": location,
                    "date": date,
                }.items()
            )
            status_changed = item["status"] != status

            db.execute(
                """
                UPDATE items
                SET report_type = ?, item_name = ?, category = ?, color = ?,
                    location = ?, country = ?, region = ?, city = ?, area = ?,
                    date = ?, description = ?, status = ?, image_filename = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    report_type,
                    item_name,
                    category,
                    color or None,
                    location,
                    country,
                    region,
                    city,
                    area,
                    date,
                    description or None,
                    status,
                    image_filename,
                    item_id,
                    g.user["id"],
                ),
            )
            if major_changed or status_changed:
                invalidate_match_state_for_item(db, item_id, preserve_conversations=True)
            db.commit()
            if item["image_filename"] and item["image_filename"] != image_filename:
                delete_image(item["image_filename"])
            flash("Your report has been updated.", "success")
            return redirect(url_for("reports.my_reports"))

    return render_template("edit_item.html", item=item, countries=location_options_country())


@bp.route("/my-reports")
@login_required
def my_reports():
    items = get_db().execute(
        "SELECT * FROM items WHERE user_id = ? ORDER BY id DESC",
        (g.user["id"],),
    ).fetchall()
    return render_template("my_reports.html", items=items)


@bp.route("/items/<int:item_id>/matches")
def possible_matches(item_id):
    db = get_db()
    current_user_id = g.user["id"] if g.user else None
    lost_item = db.execute(
        "SELECT * FROM items WHERE id = ? AND report_type = 'lost' AND status = 'open'",
        (item_id,),
    ).fetchone()
    if lost_item is None:
        abort(404)

    matches = db.execute(
        """
        SELECT found.*,
               CASE
                   WHEN lost.user_id IS NOT NULL
                    AND found.user_id IS NOT NULL
                    AND found.user_id != lost.user_id
                    AND (? = lost.user_id OR ? = found.user_id)
                   THEN 1 ELSE 0
               END AS can_start_conversation
        FROM items AS found
        JOIN items AS lost ON lost.id = ?
        WHERE found.report_type = 'found'
          AND lost.status = 'open'
          AND found.status = 'open'
        ORDER BY ABS(JULIANDAY(found.date) - JULIANDAY(lost.date)),
                 found.id DESC
        """,
        (current_user_id, current_user_id, item_id),
    ).fetchall()
    scored_matches = []
    for match in matches:
        scored = dict(match)
        scored.update(score_match(lost_item, match))
        if scored["match_score"] >= POSSIBLE_MATCH_THRESHOLD:
            scored_matches.append(scored)
    scored_matches.sort(key=lambda item: (-item["match_score"], -item["id"]))

    return render_template(
        "possible_matches.html",
        lost_item=lost_item,
        matches=scored_matches,
    )


def scored_detail_matches(db, item):
    if item["status"] != "open":
        return []

    current_user_id = g.user["id"] if g.user else None
    if item["report_type"] == "lost":
        if current_user_id is None:
            owner_condition = "1 = 1"
            parameters = ()
        elif item["user_id"] == current_user_id:
            owner_condition = "user_id IS NOT NULL AND user_id != ?"
            parameters = (current_user_id,)
        else:
            owner_condition = "user_id = ?"
            parameters = (current_user_id,)
        rows = db.execute(
            f"""
            SELECT *
            FROM items
            WHERE report_type = 'found'
              AND status = 'open'
              AND {owner_condition}
            """,
            parameters,
        ).fetchall()
        pairs = ((item, row) for row in rows)
    else:
        if current_user_id is None:
            owner_condition = "1 = 1"
            parameters = ()
        elif item["user_id"] == current_user_id:
            owner_condition = "user_id IS NOT NULL AND user_id != ?"
            parameters = (current_user_id,)
        else:
            owner_condition = "user_id = ?"
            parameters = (current_user_id,)
        rows = db.execute(
            f"""
            SELECT *
            FROM items
            WHERE report_type = 'lost'
              AND status = 'open'
              AND {owner_condition}
            """,
            parameters,
        ).fetchall()
        pairs = ((row, item) for row in rows)

    matches = []
    for lost_item, found_item in pairs:
        scored = score_match(lost_item, found_item)
        if scored["match_score"] >= POSSIBLE_MATCH_THRESHOLD:
            matches.append(
                {
                    "lost_item_id": lost_item["id"],
                    "found_item_id": found_item["id"],
                    **scored,
                }
            )
    matches.sort(key=lambda match: -match["match_score"])
    return matches


@bp.route("/items/<int:item_id>")
def item_details(item_id):
    db = get_db()
    item = db.execute(
        """
        SELECT items.*, users.username
        FROM items
        LEFT JOIN users ON users.id = items.user_id
        WHERE items.id = ?
        """,
        (item_id,),
    ).fetchone()
    if item is None:
        abort(404)

    relevant_matches = scored_detail_matches(db, item)
    best_match = relevant_matches[0] if relevant_matches else None
    return render_template(
        "report_details.html",
        item=item,
        best_match=best_match,
        can_message_user=best_match is not None,
    )


@bp.route("/items")
def browse_items():
    search = request.args.get("search", "").strip()
    report_type = request.args.get("report_type", "").strip()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    conditions = []
    parameters = []

    if search:
        conditions.append("(items.item_name LIKE ? OR items.description LIKE ?)")
        search_term = f"%{search}%"
        parameters.extend((search_term, search_term))
    if report_type in {"lost", "found"}:
        conditions.append("items.report_type = ?")
        parameters.append(report_type)
    else:
        report_type = ""
    if category:
        conditions.append("items.category = ?")
        parameters.append(category)
    if location:
        conditions.append("items.location = ?")
        parameters.append(location)

    query = """
        SELECT items.*, users.username
        FROM items
        LEFT JOIN users ON users.id = items.user_id
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY items.id DESC"

    db = get_db()
    items = db.execute(query, parameters).fetchall()
    categories = db.execute(
        "SELECT DISTINCT category FROM items ORDER BY category COLLATE NOCASE"
    ).fetchall()
    locations = db.execute(
        "SELECT DISTINCT location FROM items ORDER BY location COLLATE NOCASE"
    ).fetchall()

    filters = {
        "search": search,
        "report_type": report_type,
        "category": category,
        "location": location,
    }
    return render_template(
        "browse_items.html",
        items=items,
        categories=categories,
        locations=locations,
        filters=filters,
        filters_active=any(filters.values()),
    )


@bp.route("/report", methods=("GET", "POST"))
def report_item():
    if request.method == "POST":
        if g.user is None:
            flash("Log in to continue.", "error")
            return redirect(url_for("auth.login"))

        report_type = request.form.get("report_type", "").strip()
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "").strip()
        color = request.form.get("color", "").strip()
        country = request.form.get("country", "").strip()
        region = request.form.get("region", "").strip()
        city = request.form.get("city", "").strip()
        area = request.form.get("area", "").strip()
        date = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip()

        if report_type not in {"lost", "found"}:
            flash("Choose whether the item was lost or found.", "error")
        elif not all((item_name, category, date)):
            flash("Complete all required fields.", "error")
        elif validation_error := validate_report_fields(item_name, category, color, date, description):
            flash(validation_error, "error")
        elif not is_valid_location(country, region, city, area):
            flash("Choose a valid country, region, city, and area.", "error")
        else:
            try:
                image_filename = save_image(request.files.get("photo"))
            except ValueError as error:
                flash(str(error), "error")
                return render_template(
                    "report_item.html", countries=location_options_country()
                )

            db = get_db()
            location = compose_location(area, city, region, country)
            db.execute(
                """
                INSERT INTO items
                    (user_id, report_type, item_name, category, color, location,
                     country, region, city, area, date, description,
                     image_filename, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    report_type,
                    item_name,
                    category,
                    color or None,
                    location,
                    country,
                    region,
                    city,
                    area,
                    date,
                    description or None,
                    image_filename,
                    "open",
                ),
            )
            db.commit()
            flash("Your report has been submitted.", "success")
            return redirect(url_for("reports.report_item"))

    return render_template("report_item.html", countries=location_options_country())
