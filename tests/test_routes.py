#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "laneorchestrator" / "scripts" / "route.py"


def route(*args: str) -> dict[str, object]:
    result = subprocess.run(["python3", str(SCRIPT), *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main() -> None:
    assert route("--objective", "fix a typo in the readme", "--known-area", "--acceptance-criteria", "--files", "1")["lane"] == "luna"
    assert route("--objective", "add a dashboard filter", "--files", "4")["lane"] == "terra"
    assert route("--objective", "migrate OAuth authentication schema", "--files", "5")["lane"] == "sol-plan-terra-sol-review"
    print("route fixtures passed")


if __name__ == "__main__":
    main()
