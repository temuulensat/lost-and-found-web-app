"""Create and restore a verified archive of SQLite and report photos.

Stop the web service while creating an archive so the SQLite snapshot and
photos describe the same point in time. Store the result off the VM.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

DATABASE_NAME = "lost_and_found.sqlite"


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_archive(data_dir, output):
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    database = data_dir / DATABASE_NAME
    if not database.is_file():
        raise ValueError(f"Database not found: {database}")
    if output.exists():
        raise FileExistsError(output)
    if os.path.commonpath((str(data_dir), str(output))) == str(data_dir):
        raise ValueError("Write backups outside APP_DATA_DIR")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        snapshot = staging / DATABASE_NAME
        with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        files = {DATABASE_NAME: _digest(snapshot)}
        upload_dir = data_dir / "uploads"
        if upload_dir.exists():
            for photo in sorted(upload_dir.iterdir()):
                if not photo.is_file() or photo.is_symlink():
                    raise ValueError(f"Unexpected upload entry: {photo}")
                staged_photo = staging / "uploads" / photo.name
                staged_photo.parent.mkdir(exist_ok=True)
                shutil.copy2(photo, staged_photo)
                files[f"uploads/{photo.name}"] = _digest(staged_photo)
        manifest = {
            "format": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "files": files,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".backup-", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            with tarfile.open(temp_path, "w:gz") as archive:
                for name in sorted(files):
                    archive.add(staging / name, arcname=name, recursive=False)
                archive.add(staging / "manifest.json", arcname="manifest.json", recursive=False)
            temp_path.replace(output)
        finally:
            temp_path.unlink(missing_ok=True)
    return output


def restore_archive(archive_path, data_dir):
    archive_path, data_dir = Path(archive_path).resolve(), Path(data_dir).resolve()
    if data_dir.exists():
        raise FileExistsError(f"Restore target already exists: {data_dir}")
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=data_dir.parent))
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            manifest_member = archive.getmember("manifest.json")
            manifest = json.load(archive.extractfile(manifest_member))
            if manifest.get("format") != 1 or not isinstance(manifest.get("files"), dict):
                raise ValueError("Unsupported backup format")
            names = set(archive.getnames())
            if names != set(manifest["files"]) | {"manifest.json"}:
                raise ValueError("Backup file list does not match manifest")
            for name, expected_hash in manifest["files"].items():
                path = Path(name)
                if name != DATABASE_NAME and not (
                    len(path.parts) == 2 and path.parts[0] == "uploads" and path.name not in {".", ".."}
                ):
                    raise ValueError(f"Unsafe backup path: {name}")
                member = archive.getmember(name)
                if not member.isfile():
                    raise ValueError(f"Backup entry is not a file: {name}")
                destination = staging / path
                destination.parent.mkdir(exist_ok=True)
                with archive.extractfile(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if _digest(destination) != expected_hash:
                    raise ValueError(f"Checksum mismatch: {name}")
        if not (staging / DATABASE_NAME).is_file():
            raise ValueError("Backup has no database")
        with sqlite3.connect(staging / DATABASE_NAME) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        staging.replace(data_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return data_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--data-dir", default=os.environ.get("APP_DATA_DIR", "instance"))
    parser.add_argument("--archive", required=True)
    args = parser.parse_args()
    if args.action == "backup":
        result = create_archive(args.data_dir, args.archive)
    else:
        result = restore_archive(args.archive, args.data_dir)
    print(result)


if __name__ == "__main__":
    main()
