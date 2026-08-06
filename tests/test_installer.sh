#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
target=$(mktemp -d)
trap 'rm -rf "$target"' EXIT

sh "$root/scripts/install-agents.sh" --target "$target"
count=$(find "$target" -name 'laneorchestrator-*.toml' -type f | wc -l | tr -d ' ')
[ "$count" = 4 ]
sh "$root/scripts/install-agents.sh" --check --target "$target"
printf 'name = "foreign"\n' > "$target/laneorchestrator-router.toml"
if sh "$root/scripts/install-agents.sh" --target "$target"; then
  printf '%s\n' 'installer accepted a conflicting profile' >&2
  exit 1
fi
grep -q 'name = "foreign"' "$target/laneorchestrator-router.toml"
printf 'installer fixture passed\n'
