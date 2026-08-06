#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
target=$(mktemp -d)
outside=$(mktemp -d)
target_link=$(mktemp -d)
trap 'rm -rf "$target" "$outside" "$target_link"' EXIT

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

rm "$target/laneorchestrator-sol-reviewer.toml"
ln -s "$outside/escaped-profile.toml" "$target/laneorchestrator-sol-reviewer.toml"
if sh "$root/scripts/install-agents.sh" --target "$target"; then
  printf '%s\n' 'installer accepted a dangling profile symlink' >&2
  exit 1
fi
[ ! -e "$outside/escaped-profile.toml" ]

ln -s "$outside" "$target_link/agents"
if sh "$root/scripts/install-agents.sh" --target "$target_link/agents"; then
  printf '%s\n' 'installer accepted a symlinked target directory' >&2
  exit 1
fi
[ -z "$(find "$outside" -type f -name 'laneorchestrator-*.toml' -print -quit)" ]
printf 'installer fixture passed\n'
