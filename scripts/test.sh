#!/usr/bin/env bash
#
# Run the whole quality gate: the scripts' syntax check (bash -n), then for the consumer lint and
# formatting (ruff), typecheck (mypy) and the tests (pytest).
#
#   ./scripts/test.sh
#
# The first run creates consumer/.venv and installs consumer/requirements-dev.txt, which holds
# the image's pinned dependencies and the pinned tools; a later edit of either requirements file
# reinstalls. Needs python3 3.13 or newer.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

case "${1:-}" in -h|--help) print_help; exit 0 ;; "") ;; *) print_help >&2; exit 2 ;; esac

VENV="$CONSUMER/.venv"
# A copy of both requirements files taken after the last successful install; the venv is current
# only while it equals them.
STAMP="$VENV/.dependencies.stamp"

echo "--> scripts (bash -n)"
for script in "$ROOT"/scripts/*.sh; do bash -n "$script"; done

[ -d "$VENV" ] || python3 -m venv "$VENV"
if ! cat "$CONSUMER/requirements.txt" "$CONSUMER/requirements-dev.txt" | cmp -s - "$STAMP"; then
  echo "Installing dependencies into consumer/.venv..."
  "$VENV/bin/pip" install --quiet --disable-pip-version-check \
    -r "$CONSUMER/requirements-dev.txt"
  cat "$CONSUMER/requirements.txt" "$CONSUMER/requirements-dev.txt" > "$STAMP"
fi

cd "$CONSUMER"
echo "--> lint (ruff)"
"$VENV/bin/ruff" check .
echo "--> format (ruff format --check)"
"$VENV/bin/ruff" format --check .
echo "--> typecheck (mypy)"
"$VENV/bin/mypy"
echo "--> tests (pytest)"
"$VENV/bin/pytest"
echo "All checks passed."
