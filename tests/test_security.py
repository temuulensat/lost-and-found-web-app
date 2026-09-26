from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import os
import sqlite3

from PIL import Image, PngImagePlugin

from app import create_app
from app.db import get_db
from app import location_data


class SecurityTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE": root / "app.sqlite",
            "UPLOAD_FOLDER": root / "uploads",
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data=None):
        self.client.get('/signup')
        with self.client.session_transaction() as browser_session:
            token = browser_session['csrf_token']
        return self.client.post(path, data={**(data or {}), 'csrf_token': token})

    def signup(self):
        response = self.post('/signup', {
            'username': 'alice', 'email': 'alice@example.com', 'password': 'password123',
        })
        self.assertEqual(response.status_code, 302)

    def report_data(self, **changes):
        return {
            'report_type': 'lost', 'item_name': 'Wallet', 'category': 'Wallets',
            'color': 'Black', 'country': 'United States', 'region': 'California',
            'city': 'Acalanes Ridge', 'area': 'Other / Not listed',
            'date': '2026-09-01', 'description': 'Black wallet', **changes,
        }

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {'SECRET_KEY': ''}):
            with self.assertRaisesRegex(RuntimeError, 'SECRET_KEY'):
                create_app()

    def test_production_configuration_uses_persistent_data_dir(self):
        data_dir = Path(self.tmp.name) / 'persistent'
        with patch.dict(os.environ, {
            'SECRET_KEY': 'x' * 64,
            'APP_DATA_DIR': str(data_dir),
            'APP_TRUSTED_HOSTS': 'lost.example.com',
        }):
            app = create_app()
        self.assertEqual(Path(app.config['DATABASE']), data_dir / 'lost_and_found.sqlite')
        self.assertEqual(Path(app.config['LOCATION_DATABASE']), data_dir / 'locations.sqlite')
        self.assertEqual(Path(app.config['UPLOAD_FOLDER']), data_dir / 'uploads')
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        self.assertEqual(app.config['TRUSTED_HOSTS'], ['lost.example.com'])
        self.assertTrue((data_dir / 'lost_and_found.sqlite').exists())

    def test_location_database_builds_at_runtime_when_packaged_database_is_missing(self):
        runtime_location_db = Path(self.tmp.name) / 'runtime-locations.sqlite'

        def fake_build(database):
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
                INSERT INTO countries (code, name) VALUES ('US', 'United States');
                """
            )
            db.close()

        self.app.config['LOCATION_DATABASE'] = runtime_location_db
        with self.app.app_context():
            with patch.object(location_data, 'PACKAGED_LOCATION_DATABASE', Path(self.tmp.name) / 'missing.sqlite'):
                with patch('app.data.build_locations.build', side_effect=fake_build):
                    self.assertEqual(
                        location_data.location_options_country(),
                        [{'code': 'US', 'name': 'United States'}],
                    )
        self.assertTrue(runtime_location_db.exists())

    def test_first_public_signup_is_not_admin(self):
        self.signup()
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT is_admin FROM users').fetchone()[0], 0)

    def test_csrf_rejects_missing_and_invalid_tokens(self):
        self.client.get('/signup')
        details = {'username': 'alice', 'email': 'alice@example.com', 'password': 'password123'}
        self.assertEqual(self.client.post('/signup', data=details).status_code, 400)
        self.assertEqual(self.client.post('/signup', data={**details, 'csrf_token': 'forged'}).status_code, 400)
        self.assertEqual(self.post('/signup', details).status_code, 302)
        self.assertEqual(self.client.post('/logout').status_code, 400)
        self.assertEqual(self.post('/logout').status_code, 302)

    def test_invalid_report_date_and_category_are_rejected(self):
        self.signup()
        for changes in ({'date': '2026-02-30'}, {'category': 'Anything'}, {'item_name': 'X' * 201}):
            response = self.post('/report', self.report_data(**changes))
            self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM items').fetchone()[0], 0)

    def test_upload_is_reencoded_and_private(self):
        self.signup()
        image = Image.new('RGB', (2, 2), 'red')
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Secret', 'must be removed')
        raw = BytesIO()
        image.save(raw, format='PNG', pnginfo=metadata)
        raw.seek(0)
        response = self.post('/report', self.report_data(photo=(raw, 'photo.png')))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            filename = get_db().execute('SELECT image_filename FROM items').fetchone()[0]
        private_path = Path(self.app.config['UPLOAD_FOLDER']) / filename
        self.assertTrue(private_path.is_file())
        self.assertNotIn(b'must be removed', private_path.read_bytes())
        self.assertNotIn('/static/', str(private_path))
        photo_response = self.client.get(f'/report-photos/{filename}')
        self.assertEqual(photo_response.status_code, 200)
        photo_response.close()
        self.post('/logout')
        public_photo_response = self.client.get(f'/report-photos/{filename}')
        self.assertEqual(public_photo_response.status_code, 200)
        public_photo_response.close()

    def test_malformed_image_is_rejected(self):
        self.signup()
        forged = BytesIO(b'\x89PNG\r\n\x1a\n' + b'garbage')
        response = self.post('/report', self.report_data(photo=(forged, 'photo.png')))
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM items').fetchone()[0], 0)
