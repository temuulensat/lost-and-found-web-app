import unittest

from app.matching import POSSIBLE_MATCH_THRESHOLD, score_match


def item(**overrides):
    data = {
        "item_name": "Black leather wallet",
        "category": "Wallets",
        "color": "Black",
        "location": "Other / Not listed, Acalanes Ridge, California, United States",
        "country": "United States",
        "region": "California",
        "city": "Acalanes Ridge",
        "area": "Other / Not listed",
        "date": "2026-09-01",
        "description": "A black leather wallet with student ID inside.",
    }
    data.update(overrides)
    return data


class MatchScoringTests(unittest.TestCase):
    def test_strong_match_scores_high_and_explains_reasons(self):
        result = score_match(
            item(),
            item(
                item_name="black wallet",
                description="Black leather wallet with an ID card.",
                date="2026-09-03",
            ),
        )

        self.assertGreaterEqual(result["match_score"], POSSIBLE_MATCH_THRESHOLD)
        reason_keys = [reason["key"] for reason in result["match_reasons"]]
        self.assertEqual(
            reason_keys[:4],
            [
                "Same category",
                "Same color",
                "Same area",
                "Reported {days} days apart",
            ],
        )
        self.assertEqual(result["match_reasons"][3]["values"]["days"], 2)

    def test_weak_match_scores_below_threshold(self):
        result = score_match(
            item(),
            item(
                item_name="Silver laptop",
                category="Electronics",
                color="Silver",
                location="Other / Not listed, Accord, New York, United States",
                region="New York",
                city="Accord",
                date="2026-11-01",
                description="Laptop computer in a gray sleeve.",
            ),
        )

        self.assertLess(result["match_score"], POSSIBLE_MATCH_THRESHOLD)

    def test_description_similarity_contributes_to_score(self):
        base = item(item_name="Wallet", description="has a blue train pass and initials TM")
        without_description = item(
            item_name="Wallet",
            description="",
            date="2026-09-01",
        )
        with_description = item(
            item_name="Wallet",
            description="blue train pass with initials TM",
            date="2026-09-01",
        )

        low = score_match(base, without_description)
        high = score_match(base, with_description)

        self.assertGreater(high["match_score"], low["match_score"])
        self.assertIn(
            "Similar description",
            [reason["key"] for reason in high["match_reasons"]],
        )


if __name__ == "__main__":
    unittest.main()
