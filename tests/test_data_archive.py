from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.data_archive import create_archive, restore_archive


class DataArchiveTests(unittest.TestCase):
    def test_backup_restores_database_and_photos(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "live"
            photos = data / "uploads"
            photos.mkdir(parents=True)
            with sqlite3.connect(data / "lost_and_found.sqlite") as database:
                database.execute("CREATE TABLE users (name TEXT)")
                database.execute("INSERT INTO users VALUES ('alice')")
            (photos / "photo.jpg").write_bytes(b"example photo bytes")
            archive = create_archive(data, root / "backup.tar.gz")
            restored = restore_archive(archive, root / "restored")
            with sqlite3.connect(restored / "lost_and_found.sqlite") as database:
                self.assertEqual(database.execute("SELECT name FROM users").fetchone()[0], "alice")
            self.assertEqual((restored / "uploads" / "photo.jpg").read_bytes(), b"example photo bytes")
            with self.assertRaises(FileExistsError):
                restore_archive(archive, restored)

    def test_backup_refuses_same_data_directory(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary) / "live"
            data.mkdir()
            with sqlite3.connect(data / "lost_and_found.sqlite") as database:
                database.execute("CREATE TABLE example (id INTEGER)")
            with self.assertRaises(ValueError):
                create_archive(data, data / "backup.tar.gz")
