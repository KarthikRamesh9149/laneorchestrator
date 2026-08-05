#!/bin/sh
set -eu

usage() { printf '%s\n' 'Usage: install-agents.sh [--check] [--target DIRECTORY]'; exit 64; }
check_only=false
target="${HOME}/.codex/agents"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) check_only=true ;;
    --target) shift; [ "$#" -gt 0 ] || usage; target=$1 ;;
    *) usage ;;
  esac
  shift
done

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
templates_dir=$(CDPATH='' cd -- "$script_dir/../agents" && pwd)
python_bin=${PYTHON:-python3}
"$python_bin" - "$templates_dir" <<'PY'
import re
import sys
from pathlib import Path
field = re.compile(r'^\s*(name|description|model|model_reasoning_effort|sandbox_mode)\s*=\s*"(.+)"\s*$', re.MULTILINE)
for path in sorted(Path(sys.argv[1]).glob("*.toml")):
    data = dict(field.findall(path.read_text(encoding="utf-8")))
    for key in ("name", "description", "model", "model_reasoning_effort", "sandbox_mode"):
        if not data.get(key):
            raise SystemExit(f"Invalid {path.name}: missing {key}")
PY

if [ "$check_only" = false ]; then mkdir -p -- "$target"; fi
conflict=false
for template in "$templates_dir"/*.toml; do
  name=$(basename -- "$template")
  destination="$target/$name"
  if [ -e "$destination" ]; then
    if cmp -s -- "$template" "$destination"; then printf 'unchanged %s\n' "$name"; else printf 'conflict %s (left untouched)\n' "$destination" >&2; conflict=true; fi
  elif [ "$check_only" = true ]; then
    printf 'missing %s\n' "$destination"
  else
    cp -- "$template" "$destination"
    printf 'installed %s\n' "$name"
  fi
done
[ "$conflict" = false ] || exit 2
