"""Reduced capability-ranking fixture adapted from laneorchestrator.discovery."""

import re


STOP_WORDS = {"a", "an", "and", "for", "from", "in", "of", "the", "to", "with"}
TOKEN_ALIASES = {"js": "javascript", "auth": "authentication", "k8s": "kubernetes"}
TRUST_ORDER = {"system": 3, "user": 2, "plugin-cache": 1, "project": 0}
WORD_RE = re.compile(r"[a-z0-9]+")


def rank_capabilities(query, capabilities, limit=3):
    """Return the best matching capability records."""

    raise NotImplementedError("capability ranking is not implemented")
