#!/usr/bin/env bash
set -euo pipefail

# Run from any directory; the Python implementation resolves the repository
# root and never interpolates user input into a shell command.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/changelog.py" "$@"
