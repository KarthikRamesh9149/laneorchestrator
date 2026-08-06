#!/bin/sh
set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
python_bin=${PYTHON:-python3}
exec "$python_bin" "$script_dir/install_agents.py" "$@"
