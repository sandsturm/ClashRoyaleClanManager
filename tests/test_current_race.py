import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_rule_engine import RULES

import ClashRoyaleClanManager as app


class CurrentRiverRaceTests(unittest.TestCase):
    def setUp(self):
        self.members = {
            "items": [
                {"tag": "#A", "name": "illyrian", "role": "member"},
                {"tag": "#B", "name": "axuerky", "role": "member"},
            ]
        }
        self.current = {
            "periodType": "warDay",
            "sectionIndex": 1,
            "clan": {
                "tag": "#CLAN",
                "participants": [
                    {"tag": "#A", "fame": 0, "decksUsed": 0},
                    {"tag": "#B", "fame": 2250, "decksUsed": 12},
                ],
            },
        }

    def test_live_payload_uses_clan_participants_not_items(self):
        app.validate_api_data(self.current, "currentriverrace")
        result = app.current_race_summary(self.current, "#CLAN", self.members)
        self.assertEqual(result[0]["fame"], 0)
        self.assertEqual(result[1]["fame"], 2250)

    def test_no_record_is_unknown_not_zero(self):
        self.current["clan"]["participants"] = []
        result = app.current_race_summary(self.current, "#CLAN", self.members)
        self.assertIsNone(result[0]["fame"])
        self.assertFalse(result[0]["record_present"])

    def test_ongoing_war_does_not_trigger_kick(self):
        from rule_engine import evaluate_clan

        _, results = evaluate_clan(self.members, {"items": []}, "#CLAN", RULES)
        self.assertIsNone(results["#A"]["recommendations"]["kick"])
        self.assertIsNone(results["#B"]["recommendations"]["kick"])

    def test_live_data_cannot_replace_completed_wars(self):
        from rule_engine import evaluate_clan

        historical = {
            "items": [
                {
                    "seasonId": 2,
                    "sectionIndex": 0,
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#A", "fame": 900, "decksUsed": 12}
                                ],
                            }
                        }
                    ],
                }
            ]
        }
        _, results = evaluate_clan(self.members, historical, "#CLAN", RULES)
        self.assertFalse(results["#A"]["recommendations"]["kick"])

    def test_wrong_clan_tag_is_rejected(self):
        with self.assertRaises(RuntimeError):
            app.current_race_summary(self.current, "#OTHER", self.members)


if __name__ == "__main__":
    unittest.main()
