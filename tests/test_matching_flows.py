from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import create_app
from app.db import get_db


COUNTRY = "United States"
REGION = "California"
CITY = "Acalanes Ridge"
AREA = "Other / Not listed"


class MatchingFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": tmp_path / "test.sqlite",
                "UPLOAD_FOLDER": tmp_path / "uploads",
                "SECRET_KEY": "test",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data=None):
        self.client.get("/signup")
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        return self.client.post(path, data={**(data or {}), "csrf_token": token})

    def signup(self, username):
        response = self.post(
            "/signup",
            data={
                "username": username,
                "email": f"{username}@example.com",
                "password": "password123",
            },
        )
        self.assertEqual(response.status_code, 302)

    def login(self, username):
        response = self.post(
            "/login", data={"username": username, "password": "password123"}
        )
        self.assertEqual(response.status_code, 302)

    def logout(self):
        response = self.post("/logout")
        self.assertEqual(response.status_code, 302)

    def report(self, report_type, name, category="Wallets", color="Black"):
        response = self.post(
            "/report",
            data={
                "report_type": report_type,
                "item_name": name,
                "category": category,
                "color": color,
                "country": COUNTRY,
                "region": REGION,
                "city": CITY,
                "area": AREA,
                "date": "2026-09-01",
                "description": "A black leather wallet with student ID inside.",
            },
        )
        self.assertEqual(response.status_code, 302)

    def make_matching_reports(self):
        self.signup("alice")
        self.report("lost", "Black leather wallet")
        self.logout()
        self.signup("bob")
        self.report("found", "black wallet")
        self.logout()

    def test_possible_matches_show_percentage_and_explanation(self):
        self.make_matching_reports()
        self.login("alice")

        response = self.client.get("/items/1/matches")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("% Match", body)
        self.assertIn("Same category", body)
        self.assertIn("Same color", body)
        self.assertIn("Same area", body)
        self.assertIn("Reported same day", body)

    def test_matches_page_keeps_claim_and_conversation_actions(self):
        self.make_matching_reports()
        self.login("alice")

        response = self.client.get("/matches")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("% Match", body)
        self.assertIn("Claim Match", body)
        self.assertIn("Message Finder", body)

    def test_browse_items_links_to_report_details(self):
        self.make_matching_reports()
        self.login("alice")

        response = self.client.get("/items")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn('href="/items/1"', body)
        self.assertIn('href="/items/2"', body)
        self.assertIn("View details", body)

    def test_demo_visitors_can_browse_with_full_navigation(self):
        self.make_matching_reports()

        response = self.client.get("/items")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Lost &amp; Found Feed", body)
        self.assertIn('href="/items/1"', body)
        self.assertIn("Report Item", body)
        self.assertIn("My Reports", body)
        self.assertIn("Matches", body)
        self.assertIn("Conversations", body)
        self.assertIn("Log In", body)
        self.assertIn("Sign Up", body)

    def test_demo_visitors_can_view_details_with_login_message_action(self):
        self.make_matching_reports()

        response = self.client.get("/items/1")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Black leather wallet", body)
        self.assertIn("% Match", body)
        self.assertIn("Message User", body)
        self.assertIn('href="/login"', body)
        self.assertIn("Report Item", body)
        self.assertIn("My Reports", body)
        self.assertIn("Matches", body)
        self.assertIn("Conversations", body)
        self.assertIn("Log In", body)
        self.assertIn("Sign Up", body)
        self.assertIn("View possible matches", body)

    def test_demo_visitors_can_view_possible_matches_read_only(self):
        self.make_matching_reports()

        response = self.client.get("/items/1/matches")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Possible Matches", body)
        self.assertIn("% Match", body)
        self.assertIn("Same category", body)
        self.assertIn("Report Item", body)
        self.assertIn("My Reports", body)
        self.assertIn("Matches", body)
        self.assertIn("Conversations", body)
        self.assertIn("Log In", body)
        self.assertIn("Sign Up", body)
        self.assertIn("Message User", body)
        self.assertIn('href="/login"', body)

    def test_demo_visitors_can_explore_report_form_and_location_selectors(self):
        form_response = self.client.get("/report")

        self.assertEqual(form_response.status_code, 200)
        form_body = form_response.data.decode()
        self.assertIn("Report an item", form_body)
        self.assertIn("Report type", form_body)
        self.assertIn("Location", form_body)
        self.assertIn("Log In", form_body)
        self.assertIn("Sign Up", form_body)

        regions_response = self.client.get(f"/locations/regions?country={COUNTRY}")
        self.assertEqual(regions_response.status_code, 200)
        self.assertIsInstance(regions_response.json, list)

        submit_response = self.post(
            "/report",
            data={
                "report_type": "lost",
                "item_name": "Demo wallet",
                "category": "Wallets",
                "color": "Black",
                "country": COUNTRY,
                "region": REGION,
                "city": CITY,
                "area": AREA,
                "date": "2026-09-01",
                "description": "Demo report",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        self.assertIn("/login", submit_response.headers["Location"])

    def test_demo_keeps_protected_actions_login_gated(self):
        self.make_matching_reports()

        protected_paths = ("/my-reports", "/matches", "/conversations")
        for path in protected_paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_landing_links_to_browse_for_demo(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn('href="/items"', body)
        self.assertIn("Log In", body)
        self.assertIn("Sign Up", body)

    def test_report_details_show_fields_match_and_message_action(self):
        self.make_matching_reports()
        self.login("alice")

        response = self.client.get("/items/1")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Black leather wallet", body)
        self.assertIn("Lost", body)
        self.assertIn("Wallets", body)
        self.assertIn("Black", body)
        self.assertIn(f"{AREA}, {CITY}, {REGION}, {COUNTRY}", body)
        self.assertIn("2026-09-01", body)
        self.assertIn("A black leather wallet with student ID inside.", body)
        self.assertIn("alice", body)
        self.assertIn("Open", body)
        self.assertIn("% Match", body)
        self.assertIn("Message User", body)
        self.assertNotIn("Edit</a>", body)
        self.assertNotIn("Delete</button>", body)

    def test_report_details_hide_message_without_relevant_match(self):
        self.signup("alice")
        self.report("lost", "Black leather wallet")
        self.logout()
        self.signup("bob")
        self.report("found", "Silver laptop", category="Electronics", color="Silver")
        self.logout()
        self.login("alice")

        response = self.client.get("/items/2")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertNotIn("% Match", body)
        self.assertNotIn("Message User", body)
        self.assertNotIn("Edit</a>", body)
        self.assertNotIn("Delete</button>", body)

    def test_resolved_reports_are_excluded_from_possible_matches(self):
        self.make_matching_reports()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE items SET status = 'resolved' WHERE id = 2")
            db.commit()
        self.login("alice")

        response = self.client.get("/items/1/matches")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No possible matches yet", response.data)

    def test_conversation_cannot_start_for_below_threshold_pair(self):
        self.signup("alice")
        self.report("lost", "Black leather wallet")
        self.logout()
        self.signup("bob")
        self.report("found", "Silver laptop", category="Electronics", color="Silver")
        self.logout()
        self.login("alice")

        response = self.post("/items/1/matches/2/message")

        self.assertEqual(response.status_code, 404)

    def test_edit_keeps_existing_conversation_and_messages(self):
        self.make_matching_reports()
        self.login("alice")
        self.assertEqual(self.post("/items/1/matches/2/message").status_code, 302)
        self.assertEqual(self.post("/conversations/1", {"body": "Is this my wallet?"}).status_code, 302)
        edit = {
            "report_type": "lost", "item_name": "Leather wallet",
            "category": "Wallets", "color": "Black",
            "country": COUNTRY, "region": REGION, "city": CITY, "area": AREA,
            "date": "2026-09-01", "description": "A black wallet", "status": "open",
        }
        self.assertEqual(self.post("/items/1/edit", edit).status_code, 302)
        response = self.client.get("/conversations/1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Is this my wallet?", response.data)


if __name__ == "__main__":
    unittest.main()
