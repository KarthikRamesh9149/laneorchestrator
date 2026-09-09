import copy
import unittest

from capability_rank import rank_capabilities


CAPABILITIES = [
    {"name": "javascript-pro", "description": "Browser and Node runtime work", "source": "plugin-cache"},
    {"name": "auth-reviewer", "description": "Authentication boundary review", "source": "system"},
    {"name": "generic", "description": "General help", "source": "user"},
]


class CapabilityRankTests(unittest.TestCase):
    def test_aliases_match_name_and_description(self):
        self.assertEqual(
            rank_capabilities("JS auth", CAPABILITIES),
            [
                {"name": "auth-reviewer", "source": "system", "score": 1, "matched_terms": ["authentication"]},
                {"name": "javascript-pro", "source": "plugin-cache", "score": 1, "matched_terms": ["javascript"]},
            ],
        )

    def test_score_precedes_source_and_limit_is_applied(self):
        rows = [
            {"name": "weak", "description": "kubernetes", "source": "system"},
            {"name": "strong", "description": "Kubernetes authentication", "source": "project"},
        ]
        self.assertEqual(rank_capabilities("k8s auth", rows, 1)[0]["name"], "strong")

    def test_deduplicates_by_name_using_source_trust(self):
        rows = [
            {"name": "JS-Pro", "description": "javascript browser", "source": "project"},
            {"name": "js-pro", "description": "javascript browser", "source": "user"},
        ]
        self.assertEqual(rank_capabilities("javascript", rows), [
            {"name": "js-pro", "source": "user", "score": 1, "matched_terms": ["javascript"]},
        ])

    def test_ties_are_deterministic_and_inputs_are_unchanged(self):
        rows = [
            {"name": "Zulu", "description": "javascript", "source": "user"},
            {"name": "alpha", "description": "javascript", "source": "user"},
        ]
        before = copy.deepcopy(rows)
        self.assertEqual([row["name"] for row in rank_capabilities("the JS", rows)], ["alpha", "Zulu"])
        self.assertEqual(rows, before)

    def test_rejects_invalid_inputs(self):
        invalid = [
            ("", CAPABILITIES, 3),
            (None, CAPABILITIES, 3),
            ("js", "not-a-list", 3),
            ("js", CAPABILITIES, True),
            ("js", CAPABILITIES, 0),
            ("js", [{"name": "x", "description": "js", "source": "unknown"}], 3),
            ("js", [{"name": "x", "description": 1, "source": "user"}], 3),
        ]
        for query, rows, limit in invalid:
            with self.subTest(query=query, rows=rows, limit=limit), self.assertRaises(ValueError):
                rank_capabilities(query, rows, limit)


if __name__ == "__main__":
    unittest.main()
