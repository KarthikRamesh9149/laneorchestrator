"""Regression coverage for reviewed natural-language specialist selection."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from laneorchestrator.discovery import Capability, rank
from laneorchestrator.voltagent import PACK_PREFIX, render_pack


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "real-pack-ranking-corpus-v1.json"
HEADER = re.compile(r'(?m)^(name|description|model|model_reasoning_effort) = "([^"\n]+)"$')


def rendered_capabilities() -> list[Capability]:
    """Build discovery records from the exact rendered, namespaced pack."""
    capabilities = []
    for filename, content in render_pack().items():
        fields = dict(HEADER.findall(content.decode("utf-8")))
        capabilities.append(Capability(
            "agent", fields["name"], fields["description"], "rendered/" + filename,
            "plugin-cache", model=fields["model"], reasoning_effort=fields["model_reasoning_effort"],
        ))
    return capabilities


class RealPackRankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(CORPUS.read_text(encoding="utf-8"))
        cls.capabilities = rendered_capabilities()

    def test_reviewed_corpus_is_exactly_50_unique_natural_language_cases(self) -> None:
        self.assertEqual(len(self.cases), 50)
        self.assertEqual(len({case["id"] for case in self.cases}), 50)
        self.assertEqual(len({case["prompt"] for case in self.cases}), 50)
        self.assertTrue(all(set(case) == {"id", "prompt", "expected_specialist"} for case in self.cases))

    def test_every_reviewed_specialist_is_in_top_three_of_the_rendered_pack(self) -> None:
        misses = []
        for case in self.cases:
            actual = [item.name.removeprefix(PACK_PREFIX) for item in rank(case["prompt"], self.capabilities, ())[:3]]
            if case["expected_specialist"] not in actual:
                misses.append((case["id"], case["expected_specialist"], actual))
        self.assertEqual(misses, [])

    def test_rendered_specialists_expose_structured_terra_high_metadata(self) -> None:
        self.assertEqual(len(self.capabilities), 172)
        self.assertTrue(all(item.model == "gpt-5.6-terra" and item.reasoning_effort == "high" for item in self.capabilities))


if __name__ == "__main__":
    unittest.main()
