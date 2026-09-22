import sqlite3
from pathlib import Path


LOCATION_DATABASE = Path(__file__).parent / "data" / "locations.sqlite"
FALLBACK_OPTION = "Not available"
OTHER_AREA = "Other / Not listed"


def _connect():
    connection = sqlite3.connect(f"file:{LOCATION_DATABASE}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def location_options_country():
    with _connect() as db:
        rows = db.execute(
            "SELECT name, code FROM countries ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def location_options_regions(country_code):
    with _connect() as db:
        rows = db.execute(
            """
            SELECT name, code FROM regions
            WHERE country_code = ? ORDER BY name COLLATE NOCASE
            """,
            (country_code,),
        ).fetchall()
    return [dict(row) for row in rows] or [{"name": FALLBACK_OPTION, "code": ""}]


def location_options_cities(country_code, region_code):
    with _connect() as db:
        rows = db.execute(
            """
            SELECT DISTINCT name, name AS code FROM cities
            WHERE country_code = ? AND region_code = ?
            ORDER BY population DESC, name COLLATE NOCASE
            """,
            (country_code, region_code),
        ).fetchall()
    return [dict(row) for row in rows] or [{"name": FALLBACK_OPTION, "code": ""}]


def areas(_country_code, _region_code, _city_name):
    return [OTHER_AREA]


def is_valid_location(country_name, region_name, city_name, area_name):
    with _connect() as db:
        country = db.execute(
            "SELECT code FROM countries WHERE name = ?", (country_name,)
        ).fetchone()
        if country is None:
            return False

        regions = db.execute(
            "SELECT code, name FROM regions WHERE country_code = ?",
            (country["code"],),
        ).fetchall()
        if regions:
            region = next((row for row in regions if row["name"] == region_name), None)
            if region is None:
                return False
            city_exists = db.execute(
                """
                SELECT 1 FROM cities
                WHERE country_code = ? AND region_code = ? AND name = ? LIMIT 1
                """,
                (country["code"], region["code"], city_name),
            ).fetchone()
            city_count = db.execute(
                "SELECT 1 FROM cities WHERE country_code = ? AND region_code = ? LIMIT 1",
                (country["code"], region["code"]),
            ).fetchone()
            if city_exists is None and not (city_count is None and city_name == FALLBACK_OPTION):
                return False
        elif region_name != FALLBACK_OPTION or city_name != FALLBACK_OPTION:
            return False

    return area_name == OTHER_AREA
