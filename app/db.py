import sqlite3

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    with current_app.open_resource("schema.sql") as schema:
        db.executescript(schema.read().decode("utf-8"))
    migrate_admin_role(db)
    migrate_legacy_reports(db)
    migrate_item_images(db)
    migrate_item_location_parts(db)


def migrate_admin_role(db: sqlite3.Connection) -> None:
    user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if "is_admin" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    db.commit()


def migrate_legacy_reports(db: sqlite3.Connection) -> None:
    """Keep pre-account reports ownerless and remove the old placeholder owner."""
    item_columns = {row["name"]: row for row in db.execute("PRAGMA table_info(items)")}
    legacy_user = db.execute(
        "SELECT id FROM users WHERE username = 'legacy-reports'"
    ).fetchone()
    has_user_id = "user_id" in item_columns
    user_id_is_required = has_user_id and item_columns["user_id"]["notnull"] == 1

    if has_user_id and not user_id_is_required and legacy_user is None:
        return

    legacy_user_id = legacy_user["id"] if legacy_user else None
    if legacy_user_id is not None:
        db.execute(
            """
            DELETE FROM messages WHERE conversation_id IN (
                SELECT id FROM conversations
                WHERE lost_user_id = ? OR found_user_id = ?
            )
            """,
            (legacy_user_id, legacy_user_id),
        )
        db.execute(
            "DELETE FROM conversations WHERE lost_user_id = ? OR found_user_id = ?",
            (legacy_user_id, legacy_user_id),
        )
        db.commit()

    owner_expression = "NULL"
    if has_user_id:
        owner_expression = "user_id"
        if legacy_user_id is not None:
            owner_expression = f"CASE WHEN user_id = {legacy_user_id} THEN NULL ELSE user_id END"

    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript(
        f"""
        BEGIN;
        CREATE TABLE items_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            report_type TEXT NOT NULL CHECK (report_type IN ('lost', 'found')),
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            color TEXT,
            location TEXT NOT NULL,
            country TEXT,
            region TEXT,
            city TEXT,
            area TEXT,
            date TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        INSERT INTO items_migrated
            (id, user_id, report_type, item_name, category, color, location,
             country, region, city, area, date, description, image_filename, status)
        SELECT id, {owner_expression}, report_type, item_name, category, color,
               location, NULL, NULL, NULL, NULL, date, description, NULL, status
        FROM items;
        DROP TABLE items;
        ALTER TABLE items_migrated RENAME TO items;
        COMMIT;
        """
    )
    db.execute("PRAGMA foreign_keys = ON")
    if legacy_user_id is not None:
        db.execute("DELETE FROM users WHERE id = ?", (legacy_user_id,))
        db.commit()


def migrate_item_images(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(items)")}
    if "image_filename" not in columns:
        db.execute("ALTER TABLE items ADD COLUMN image_filename TEXT")
        db.commit()


def migrate_item_location_parts(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(items)")}
    for column in ("country", "region", "city", "area"):
        if column not in columns:
            db.execute(f"ALTER TABLE items ADD COLUMN {column} TEXT")
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
