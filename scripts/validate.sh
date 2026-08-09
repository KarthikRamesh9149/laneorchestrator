#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-python3}
cache_dir=$(mktemp -d)
trap 'rm -rf "$cache_dir"' EXIT

cd "$root"
sh -n scripts/install-agents.sh scripts/validate.sh tests/test_installer.sh
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" -m py_compile \
  laneorchestrator/__init__.py \
  laneorchestrator/__main__.py \
  laneorchestrator/diagnostics.py \
  laneorchestrator/cli.py \
  scripts/healthcheck.py \
  scripts/install_agents.py \
  skills/laneorchestrator/scripts/catalog.py \
  skills/laneorchestrator/scripts/route.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/healthcheck.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" -m unittest discover -s tests -v
