#!/usr/bin/env bash
#
# Docker Compose helper for the stack: teardown, logs, status. Bringing it up is start.sh's job.
#
#   ./scripts/docker-helper.sh --stop [--volumes]
#       Stop and remove the stack's containers and network, the local Redpanda included. The
#       data volumes (InfluxDB's points, Grafana's state, Redpanda's topics) are KEPT by default
#       so they survive a restart; --volumes (alias -v) also removes them.
#   ./scripts/docker-helper.sh --logs [SERVICE]
#       Follow the logs live (last 200 lines), of every service or of the one named
#       (kafka-to-influxdb, influxdb, grafana, redpanda, redpanda-console).
#   ./scripts/docker-helper.sh --ps
#       Show the containers' status.
#   -h, --help
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

# Every profile, so the commands also reach the Redpanda services whether or not they run.
all_services() { compose --profile '*' "$@"; }

do_stop() {
  local -a down=(down --remove-orphans)
  while [ $# -gt 0 ]; do
    case "$1" in
      -v|--volumes) down+=(-v) ;;
      *) echo "Unknown --stop option '$1'" >&2; exit 2 ;;
    esac
    shift
  done
  all_services "${down[@]}"
}

mode="${1:-}"
case "$mode" in
  -h|--help) print_help; exit 0 ;;
  --stop|--logs|--ps) shift ;;
  *) print_help >&2; exit 2 ;;
esac

require_env
require_docker
case "$mode" in
  --stop) do_stop "$@" ;;
  --logs) all_services logs -f --tail=200 "$@" ;;
  --ps)   all_services ps "$@" ;;
esac
