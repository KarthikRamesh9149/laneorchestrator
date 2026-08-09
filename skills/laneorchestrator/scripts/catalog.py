#!/usr/bin/env python3
"""Compatibility entry point for canonical bounded capability discovery."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from laneorchestrator.discovery import main


if __name__ == "__main__":
    raise SystemExit(main())
