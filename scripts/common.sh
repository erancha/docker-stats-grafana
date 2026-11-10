#!/usr/bin/env bash
# Shared helpers for the scripts: repo paths, help text, preconditions, and access to .env, to
# Docker Compose and to a URL that is still starting.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSUMER="$ROOT/consumer"
ENV_FILE="$ROOT/.env"
COMPOSE_FILE="$ROOT/docker-compose.yml"

# Print the calling script's header comment block as --help text (single source of usage docs).
print_help() { awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"; }

require_env() {
  [ -f "$ENV_FILE" ] \
    || { echo ".env not found; create it first:  ./scripts/init-env.sh" >&2; exit 1; }
}

require_docker() {
  docker info >/dev/null 2>&1 \
    || { echo "Docker is not reachable; start it and retry." >&2; exit 1; }
}

require_command() {  # command
  command -v "$1" >/dev/null 2>&1 \
    || { echo "'$1' is not installed; install it and retry." >&2; exit 1; }
}

# --env-file makes the .env values available to the ${...} interpolation of the compose file. A
# variable exported by the calling script takes precedence over the file.
compose() {
  (cd "$ROOT" && docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@")
}

# The value of KEY in an env file (the last assignment); fails loudly when it is absent or blank.
env_value() {  # file key
  local value
  value="$(sed -n "s/^$2=//p" "$1" | tail -n 1)"
  [ -n "$value" ] \
    || { echo "$2 has no value in $1; .env.example describes it" >&2; exit 1; }
  printf '%s' "$value"
}

# Waits up to about a minute until the URL answers with any HTTP status.
wait_for_http() {  # url
  curl -s --retry 60 --retry-all-errors --retry-delay 1 --max-time 2 -o /dev/null "$1"
}
