from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "laneorchestrator" / "scripts" / "route.py"

CASES = [
    # Bounded local work: Luna
    ("readme-title-typo", "Correct one typo in the README title", "luna", True, True, 1),
    ("css-color-token", "Change one documented CSS color token", "luna", True, True, 1),
    ("test-description", "Correct a misleading unit-test description", "luna", True, True, 1),
    ("log-label", "Fix one log message label", "luna", True, True, 1),
    ("doc-link", "Update one broken documentation link", "luna", True, True, 1),
    ("comment-typo", "Correct a typo in one source-code comment", "luna", True, True, 1),
    ("sample-text", "Adjust one example response string", "luna", True, True, 1),
    ("changelog-date", "Correct one changelog date", "luna", True, True, 1),
    ("button-copy", "Correct one button label in a known component", "luna", True, True, 1),
    ("readme-heading", "Rename one README heading to the approved wording", "luna", True, True, 1),
    # Normal implementation work: Terra
    ("dashboard-filter", "Add a dashboard date filter across three components", "terra", False, True, 3),
    ("csv-export", "Add CSV export to the existing report page", "terra", False, True, 3),
    ("parser-refactor", "Refactor the import parser into smaller modules", "terra", False, False, 5),
    ("empty-state", "Add an empty state to the search results flow", "terra", False, True, 2),
    ("metrics-chart", "Add a usage chart to the internal dashboard", "terra", False, False, 4),
    ("pagination", "Implement pagination for the activity feed", "terra", False, False, 4),
    ("theme-toggle", "Add a dark mode toggle to the settings screen", "terra", False, True, 3),
    ("markdown-preview", "Add markdown preview to the editor", "terra", False, False, 4),
    ("search-sorting", "Add client-side sorting to the catalog search", "terra", False, True, 3),
    ("error-boundary", "Add an error boundary around the analytics panel", "terra", False, False, 3),
    ("i18n-copy", "Add French translations for the onboarding flow", "terra", False, False, 4),
    ("component-library", "Extract shared button variants into the component library", "terra", False, False, 5),
    ("report-layout", "Rearrange the report layout for smaller screens", "terra", False, True, 3),
    ("file-upload-ui", "Add a drag-and-drop file upload interface", "terra", False, False, 4),
    ("webhook-docs", "Write integration documentation for existing webhooks", "terra", False, True, 2),
    # High-risk work: Sol plan → Terra → Sol review
    ("oauth-storage", "Migrate OAuth token storage for production", "sol-plan-terra-sol-review", False, False, 4),
    ("sso", "Enable SSO login for enterprise users", "sol-plan-terra-sol-review", False, False, 5),
    ("rbac", "Change role-based access permissions for administrators", "sol-plan-terra-sol-review", False, False, 3),
    ("password-reset", "Redesign the password reset session flow", "sol-plan-terra-sol-review", False, False, 4),
    ("secret-rotation", "Rotate API secrets without downtime", "sol-plan-terra-sol-review", False, False, 5),
    ("encryption", "Encrypt customer records at rest", "sol-plan-terra-sol-review", False, False, 6),
    ("pii", "Add PII redaction to audit logs", "sol-plan-terra-sol-review", False, False, 4),
    ("payment", "Add card payment checkout", "sol-plan-terra-sol-review", False, False, 6),
    ("refund", "Automate customer refunds", "sol-plan-terra-sol-review", False, False, 4),
    ("billing", "Change recurring billing proration", "sol-plan-terra-sol-review", False, False, 5),
    ("ledger", "Correct ledger reconciliation logic", "sol-plan-terra-sol-review", False, False, 4),
    ("invoice", "Generate tax invoices for completed orders", "sol-plan-terra-sol-review", False, False, 4),
    ("schema", "Rename a production database column", "sol-plan-terra-sol-review", False, False, 4),
    ("backfill", "Backfill missing customer identifiers", "sol-plan-terra-sol-review", False, False, 5),
    ("retention", "Purge records under the data retention policy", "sol-plan-terra-sol-review", False, False, 4),
    ("public-api", "Change the public REST endpoint response contract", "sol-plan-terra-sol-review", False, False, 4),
    ("webhook-contract", "Version outbound webhook payloads", "sol-plan-terra-sol-review", False, False, 4),
    ("race-condition", "Fix a race condition in order processing", "sol-plan-terra-sol-review", False, False, 5),
    ("idempotency", "Add idempotency to order submission", "sol-plan-terra-sol-review", False, False, 4),
    ("production-deploy", "Deploy the new service to production", "sol-plan-terra-sol-review", False, False, 3),
    ("gdpr-export", "Build a GDPR customer-data export", "sol-plan-terra-sol-review", False, False, 4),
    ("deletion", "Delete inactive customer data from production", "sol-plan-terra-sol-review", False, False, 4),
    ("bank-transfer", "Add bank transfer settlement handling", "sol-plan-terra-sol-review", False, False, 5),
    ("queue-replay", "Replay messages from the production order queue", "sol-plan-terra-sol-review", False, False, 4),
    ("signature-verification", "Verify signed webhook requests", "sol-plan-terra-sol-review", False, False, 3),
]


class RoutingMatrixTests(unittest.TestCase):
    def test_fifty_use_cases(self) -> None:
        self.assertEqual(len(CASES), 50)
        failures = []
        for name, objective, expected_lane, known_area, acceptance_criteria, files in CASES:
            command = [sys.executable, str(SCRIPT), "--objective", objective, "--files", str(files)]
            if known_area:
                command.append("--known-area")
            if acceptance_criteria:
                command.append("--acceptance-criteria")
            command.extend(["--risk-assessment", "low" if expected_lane == "luna" else "normal" if expected_lane == "terra" else "high"])
            actual = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)["lane"]
            if actual != expected_lane:
                failures.append(f"{name}: expected {expected_lane}, got {actual}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
