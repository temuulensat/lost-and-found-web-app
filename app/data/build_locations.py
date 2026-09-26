"""Build the app's read-only location database from GeoNames data files."""

import csv
import sqlite3
import zipfile
from pathlib import Path


DATA_DIR = Path(__file__).parent
DATABASE = DATA_DIR / "locations.sqlite"


def build(database=DATABASE):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()

    db = sqlite3.connect(database)
    db.executescript(
        """
        CREATE TABLE countries (code TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE regions (
            country_code TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (country_code, code)
        );
        CREATE TABLE cities (
            country_code TEXT NOT NULL,
            region_code TEXT NOT NULL,
            name TEXT NOT NULL,
            geoname_id INTEGER NOT NULL,
            population INTEGER NOT NULL,
            PRIMARY KEY (country_code, region_code, geoname_id)
        );
        CREATE INDEX regions_country_name ON regions(country_code, name COLLATE NOCASE);
        CREATE INDEX cities_region_name ON cities(country_code, region_code, name COLLATE NOCASE);
        """
    )

    countries = []
    with (DATA_DIR / "countryInfo.txt").open(encoding="utf-8") as source:
        for row in csv.reader((line for line in source if not line.startswith("#")), delimiter="\t"):
            if len(row) > 4:
                countries.append((row[0], row[4]))
    db.executemany("INSERT INTO countries (code, name) VALUES (?, ?)", countries)

    regions = []
    with (DATA_DIR / "admin1CodesASCII.txt").open(encoding="utf-8") as source:
        for row in csv.reader(source, delimiter="\t"):
            country_code, region_code = row[0].split(".", 1)
            regions.append((country_code, region_code, row[1]))
    db.executemany(
        "INSERT INTO regions (country_code, code, name) VALUES (?, ?, ?)", regions
    )
    region_names = {(country, code): name for country, code, name in regions}

    with zipfile.ZipFile(DATA_DIR / "cities500.zip") as archive:
        with archive.open("cities500.txt") as raw_source:
            source = (line.decode("utf-8") for line in raw_source)
            batch = []
            for row in csv.reader(source, delimiter="\t"):
                if len(row) < 15 or row[6] != "P":
                    continue
                name = row[1]
                region_name = region_names.get((row[8], row[10]))
                alternate_names = set(row[3].split(","))
                if row[7] == "PPLC" and region_name and region_name in alternate_names:
                    name = region_name
                batch.append((row[8], row[10], name, int(row[0]), int(row[14] or 0)))
                if len(batch) == 10000:
                    db.executemany(
                        "INSERT OR IGNORE INTO cities VALUES (?, ?, ?, ?, ?)", batch
                    )
                    batch.clear()
            db.executemany("INSERT OR IGNORE INTO cities VALUES (?, ?, ?, ?, ?)", batch)

    db.commit()
    db.execute("VACUUM")
    db.close()


if __name__ == "__main__":
    build()
