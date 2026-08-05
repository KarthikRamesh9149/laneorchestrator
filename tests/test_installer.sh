#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
target=$(mktemp -d)
trap 'rm -rf "$target"' EXIT

sh "$root/scripts/install-agents.sh" --target "$target"
count=$(find "$target" -name 'laneorchestrator-*.toml' -type f | wc -l | tr -d ' ')
[ "$count" = 4 ]
sh "$root/scripts/install-agents.sh" --check --target "$target"
printf 'installer fixture passed\n'
