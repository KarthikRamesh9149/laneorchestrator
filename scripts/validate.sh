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
  scripts/check_docs.py \
  scripts/check_manifests.py \
  scripts/build_release.py \
  scripts/verify_release.py \
  scripts/private_static_analysis.py \
  scripts/healthcheck.py \
  scripts/install_agents.py \
  skills/laneorchestrator/scripts/catalog.py \
  skills/laneorchestrator/scripts/route.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/healthcheck.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/check_docs.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/check_manifests.py
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/private_static_analysis.py \
  --source laneorchestrator --source scripts --output "$cache_dir/private-static-analysis.sarif"
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" -m laneorchestrator benchmark --json > "$cache_dir/benchmark.json"
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/build_release.py --output "$cache_dir/release"
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" scripts/verify_release.py "$cache_dir/release"
PYTHONPYCACHEPREFIX="$cache_dir" "$python_bin" -m unittest discover -s tests -v
