"""Small JSON trust-boundary fixture adapted from laneorchestrator.security."""

import json


class DuplicateJSONKeyError(ValueError):
    """Raised when an object contains an ambiguous duplicate member."""


def parse_json_object(data):
    """Parse one JSON object.

    BUG: converting the already-decoded object to ``dict`` cannot recover keys
    that ``json.loads`` silently replaced.
    """

    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("JSON value must be an object")
    return dict(value)
