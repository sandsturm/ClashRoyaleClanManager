import unittest

from rule_engine import (
    War,
    build_wars,
    donation_summary,
    evaluate_clan,
    evaluate_member,
)

RULES = {
    "promotion": {
        "enabled": True,
        "strategy": "participation",
        "roles": ["member"],
        "participation": {"consecutive_wars": 10},
        "fame": {"minimum_fame_per_week": 1600, "consecutive_wars": 2},
    },
    "demotion": {
        "enabled": True,
        "strategy": "participation",
        "roles": ["elder"],
        "participation": {"consecutive_missed_wars": 2},
        "fame": {"below_fame_per_week": 1600, "consecutive_wars": 2},
    },
    "kick": {
        "enabled": True,
        "strategy": "combined",
        "roles": ["member"],
        "operator": "OR",
        "participation": {"consecutive_missed_wars": 1},
        "fame": {"minimum_total_fame": 600, "last_wars": 1},
    },
    "warning": {
        "enabled": False,
        "strategy": "fame",
        "roles": ["member"],
        "fame": {"below_fame": 1200, "last_wars": 1},
    },
}


def history(scores, decks):
    return [
        War(10, 10 - i, {"#A": {"tag": "#A", "fame": s, "decksUsed": d}})
        for i, (s, d) in enumerate(zip(scores, decks))
    ]


class RuleEngineTests(unittest.TestCase):
    def test_promotion_ten_participations(self):
        r = evaluate_member("#A", "member", history([700] * 10, [1] * 10), RULES)
        self.assertTrue(r["promotion"])
        self.assertFalse(r["kick"])

    def test_missing_history_not_promotion(self):
        r = evaluate_member("#A", "member", history([700] * 9, [1] * 9), RULES)
        self.assertIsNone(r["promotion"])

    def test_demotion_two_missed(self):
        r = evaluate_member("#A", "elder", history([0, 0], [0, 0]), RULES)
        self.assertTrue(r["demotion"])
        self.assertFalse(r["kick"])

    def test_kick_low_fame(self):
        r = evaluate_member("#A", "member", history([599], [1]), RULES)
        self.assertTrue(r["kick"])

    def test_kick_no_decks(self):
        r = evaluate_member("#A", "member", history([700], [0]), RULES)
        self.assertTrue(r["kick"])

    def test_exactly_600_safe(self):
        r = evaluate_member("#A", "member", history([600], [1]), RULES)
        self.assertFalse(r["kick"])

    def test_missing_participant_unknown(self):
        r = evaluate_member("#A", "member", [War(10, 1, {})], RULES)
        self.assertIsNone(r["kick"])

    def test_unknown_decks_not_inactive(self):
        r = evaluate_member("#A", "member", [War(10, 1, {"#A": {"fame": 700}})], RULES)
        self.assertIsNone(r["kick"])

    def test_unknown_decks_but_low_fame_kick(self):
        r = evaluate_member("#A", "member", [War(10, 1, {"#A": {"fame": 400}})], RULES)
        self.assertTrue(r["kick"])

    def test_sort_ids_numerically(self):
        log = {
            "items": [
                {
                    "seasonId": 9,
                    "sectionIndex": 5,
                    "standings": [{"clan": {"tag": "#CLAN", "participants": []}}],
                },
                {
                    "seasonId": 10,
                    "sectionIndex": 1,
                    "standings": [{"clan": {"tag": "#CLAN", "participants": []}}],
                },
            ]
        }
        self.assertEqual(build_wars(log, "#CLAN")[0].identifier, "10:1")

    def test_donations_do_not_affect_war_recommendations(self):
        member = {
            "items": [{"tag": "#A", "name": "A", "role": "member", "donations": 4000}]
        }
        data = {
            "items": [
                {
                    "seasonId": 10,
                    "sectionIndex": 1,
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#A", "fame": 500, "decksUsed": 1}
                                ],
                            }
                        }
                    ],
                }
            ]
        }
        _, results = evaluate_clan(member, data, "#CLAN", RULES)
        self.assertTrue(results["#A"]["recommendations"]["kick"])
        self.assertEqual(donation_summary(member)["#A"]["donations"], 4000)

    def test_donation_history_resets_are_not_negative(self):
        members = {"items": [{"tag": "#A", "donations": 5, "donationsReceived": 12}]}
        history = [
            {
                "timestamp": "2026-10-01T10:00:00+00:00",
                "players": {"#A": {"donations": 4000}},
            },
            {
                "timestamp": "2026-10-08T10:00:00+00:00",
                "players": {"#A": {"donations": 5}},
            },
        ]
        result = donation_summary(members, history)["#A"]
        self.assertEqual(result["observed_resets"], 1)
        self.assertEqual(result["highest_observed_counter"], 4000)
        self.assertEqual(result["donations_received"], 12)

    def test_missing_donations_unknown(self):
        result = donation_summary({"items": [{"tag": "#A"}]})["#A"]
        self.assertIsNone(result["donations"])
        self.assertEqual(result["observations"], 0)

    def test_all_empty(self):
        wars, members = evaluate_clan({"items": []}, {"items": []}, "#CLAN", RULES)
        self.assertEqual(wars, [])
        self.assertEqual(members, {})


if __name__ == "__main__":
    unittest.main()
