# Lost & Found

A Flask and SQLite application for reporting lost and found items.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export APP_COOKIE_SECURE=0
flask --app app run --debug
```

Open `http://127.0.0.1:5000`. Keep the generated secret for the lifetime of the local database if you want existing sessions to persist. Debug mode is for local development only.

## Production deployment

Set these environment variables in the deployment platform before starting the application:

- `SECRET_KEY`: a persistent, random secret (at least 32 bytes of entropy). Do not use the development example as a shared or committed value. Changing it invalidates existing login sessions.
- `APP_DATA_DIR`: a writable, persistent directory for `lost_and_found.sqlite` and `uploads/`. Back up **both** the SQLite database and uploads. Restore them together.
- `APP_TRUSTED_HOSTS`: comma-separated public hostnames, for example `lost.example.com`.
- Leave `APP_COOKIE_SECURE` unset (its default is `1`) and serve the app only through HTTPS. Set it to `0` only for local HTTP development.

Install dependencies from `requirements.txt`, then run behind an HTTPS reverse proxy:

```bash
gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8000 'app:create_app()'
```

Keep the SQLite database on a persistent local filesystem, not an ephemeral container layer or network share. Use one Gunicorn worker while using SQLite. Set a request size limit at the reverse proxy no higher than the app's 5 MB limit. Do not expose `app/static/uploads` as a public directory; newly uploaded photos are stored under `APP_DATA_DIR/uploads` and served through the authenticated `/report-photos/` route. If upgrading a deployment that already has photos in `app/static/uploads`, move those photos to `APP_DATA_DIR/uploads` and remove the public copies before exposing the site.

The app creates its schema at startup. Back up the data directory before an upgrade, and restore it if a migration fails. Limit filesystem access to the application process and backup operator.

## Completely free deployment preparation

For an Oracle Cloud Always Free VM, persistent SQLite and uploads, a free DuckDNS hostname, HTTPS with Caddy, and backup/restore instructions, see [deploy/oci/README.md](deploy/oci/README.md). Always Free capacity and uptime are not guaranteed; keep off-VM backups before sharing a public link.

## GitHub and Render deployment

The repository should contain application code, templates, translations, tests, and the GeoNames source data in `app/data/`. It must **not** contain `.env` files, SQLite databases, `instance/` data, uploaded photos, backup archives, or a virtual environment. The generated `app/data/locations.sqlite` is intentionally excluded. Render must rebuild that read-only location database during its build.

For a Render Python web service, use:

```text
Build command: pip install -r requirements.txt && python app/data/build_locations.py
Start command: gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT 'app:create_app()'
```

Set `SECRET_KEY` in Render's environment settings to a persistent random value; do not commit it. Set `APP_TRUSTED_HOSTS` to your actual `*.onrender.com` hostname. If using a **paid** persistent disk, mount it at `/var/data` and set `APP_DATA_DIR=/var/data`; the SQLite database and uploaded photos will both live there. Keep `APP_COOKIE_SECURE=1` (the default). Existing local user data does not move to Render through GitHub; restore a private backup separately after attaching persistent storage.

**Render's free web service cannot attach a persistent disk.** With this SQLite-and-local-photos design, a free Render deployment can show a demo but will lose new reports and photos on restart or redeploy. Use a paid web service with a disk if the public app must retain user data. See [Render's Flask deployment guide](https://render.com/docs/deploy-flask) and [persistent disk limitations](https://render.com/docs/disks).
