import unittest
from unittest import mock

import route_summary


class RouteSummaryTests(unittest.TestCase):
    def test_public_results_are_preserved(self):
        self.assertEqual(
            route_summary.implementation_summary("T1", "gpt-5.6-terra", "medium", 1),
            {"task_id": "T1", "stage": "implementation", "passed": True,
             "model": "gpt-5.6-terra", "reasoning_effort": "medium"},
        )
        self.assertEqual(
            route_summary.review_summary("T1", "gpt-5.6-sol", "high", "approve"),
            {"task_id": "T1", "stage": "review", "verdict": "approve",
             "model": "gpt-5.6-sol", "reasoning_effort": "high"},
        )

    def test_validation_errors_are_preserved(self):
        for function, final in ((route_summary.implementation_summary, True),
                                (route_summary.review_summary, "approve")):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError, "unsupported model"):
                function("T1", "other", "high", final)
            with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError, "unsupported reasoning effort"):
                function("T1", "gpt-5.6-sol", "extreme", final)

    def test_both_public_functions_delegate_once_to_shared_helper(self):
        with mock.patch.object(route_summary, "_selection_payload", return_value={
            "model": "chosen", "reasoning_effort": "chosen-effort",
        }) as helper:
            implementation = route_summary.implementation_summary("T1", "m", "e", False)
            helper.assert_called_once_with("m", "e")
            self.assertEqual(implementation["model"], "chosen")
        with mock.patch.object(route_summary, "_selection_payload", return_value={
            "model": "chosen", "reasoning_effort": "chosen-effort",
        }) as helper:
            review = route_summary.review_summary("T2", "m2", "e2", "changes-requested")
            helper.assert_called_once_with("m2", "e2")
            self.assertEqual(review["reasoning_effort"], "chosen-effort")


if __name__ == "__main__":
    unittest.main()
