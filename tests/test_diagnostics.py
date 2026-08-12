from __future__ import annotations

import json
import unittest

from laneorchestrator.diagnostics import (
    CommandResult,
    Diagnostic,
    Level,
    command_result,
    error_result,
    render_human,
    render_json,
)


class DiagnosticTests(unittest.TestCase):
    def test_human_and_json_have_identical_diagnostics(self) -> None:
        result = CommandResult(
            command="doctor",
            ok=False,
            data={"version": "0.2.3"},
            diagnostics=tuple(
                Diagnostic(code=f"D{i}", level=level, message=level.value, evidence={"i": i})
                for i, level in enumerate(Level)
            ),
            errors=(),
        )
        payload = json.loads(render_json(result))
        human = render_human(result)
        self.assertEqual(payload["schema_version"], 1)
        for item in payload["diagnostics"]:
            self.assertIn(item["code"], human)
            self.assertIn(item["level"], human)
            self.assertIn(item["message"], human)

    def test_dict_field_order_is_stable(self) -> None:
        result = command_result("version", data={"version": "0.2.3"})
        self.assertEqual(
            list(result.to_dict()),
            ["schema_version", "command", "ok", "data", "diagnostics", "errors"],
        )

    def test_results_are_immutable_and_ok_is_derived(self) -> None:
        result = command_result(
            "doctor",
            diagnostics=(Diagnostic("D_FAIL", Level.FAIL, "failed", {"reason": "test"}),),
        )
        self.assertFalse(result.ok)
        with self.assertRaises(TypeError):
            result.data["new"] = "value"  # type: ignore[index]
        with self.assertRaises((AttributeError, TypeError)):
            result.diagnostics += ()  # type: ignore[misc]

    def test_error_result_is_stable_and_not_ok(self) -> None:
        result = error_result("version", "invalid_arguments", "unrecognized argument: bad")
        self.assertFalse(result.ok)
        self.assertEqual(
            result.to_dict()["errors"],
            [{"code": "invalid_arguments", "message": "unrecognized argument: bad"}],
        )


if __name__ == "__main__":
    unittest.main()
