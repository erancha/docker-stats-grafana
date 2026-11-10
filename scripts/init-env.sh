#!/usr/bin/env bash
#
# Create .env from .env.example with generated credentials. An existing .env is kept unless
# --force.
#
#   ./scripts/init-env.sh             # create .env
#   ./scripts/init-env.sh --force     # replace an existing .env, hand-edited keys included
#
# The InfluxDB token, the InfluxDB admin password and the Grafana admin password are random hex
# strings from openssl. InfluxDB applies its credentials only when its data volume is first
# created, so after --force on a stack that has run, remove the volumes too:
# ./scripts/docker-helper.sh --stop --volumes. Then run ./scripts/start.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force)   FORCE=1 ;;
    -h|--help) print_help; exit 0 ;;
    *) print_help >&2; exit 2 ;;
  esac
  shift
done

if [ -f "$ENV_FILE" ] && [ "$FORCE" -eq 0 ]; then
  echo ".env already exists; left as it is (--force overwrites it)."
  exit 0
fi
require_command openssl

GENERATED_KEYS=(INFLUXDB_TOKEN INFLUXDB_ADMIN_PASSWORD GRAFANA_ADMIN_PASSWORD)
# The new file is built and verified beside .env and renamed over it only when complete, so a
# failure leaves no partial .env. mktemp creates it readable by the owner only, as .env holds
# credentials.
draft="$(mktemp "$ENV_FILE.XXXXXX")"
trap 'rm -f "$draft"' EXIT
cp "$ROOT/.env.example" "$draft"
for key in "${GENERATED_KEYS[@]}"; do
  sed -i "s|^$key=.*|$key=$(openssl rand -hex 24)|" "$draft"
  env_value "$draft" "$key" >/dev/null
done
mv "$draft" "$ENV_FILE"
echo "Created .env with a generated InfluxDB token and admin passwords."
echo "Next: ./scripts/start.sh"
