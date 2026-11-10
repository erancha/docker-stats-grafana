#!/usr/bin/env bash
#
# Run the stats pipeline in Docker: build the consumer image and start InfluxDB, Grafana, the
# consumer and a local Redpanda broker with its console, then return once Grafana answers.
#
#   ./scripts/start.sh               # with a local Redpanda broker
#   ./scripts/start.sh --no-kafka    # without one: the consumer reads the broker named in .env
#
# With the local broker the consumer reaches it inside the Docker network as redpanda:9092,
# whatever KAFKA_BOOTSTRAP_SERVERS says; .env keeps the address this machine uses
# (localhost:9092), which collect-stats.sh publishes to.
# Published on this machine's loopback interface: Grafana at localhost:3100, InfluxDB at
# localhost:8086, and with the local broker the Kafka API at localhost:9092 and the Redpanda
# console at localhost:8080.
# Requires .env (./scripts/init-env.sh). Stop or inspect the stack with
# ./scripts/docker-helper.sh (--stop / --logs / --ps); feed it with ./scripts/collect-stats.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

GRAFANA_URL="http://localhost:3100"

WITH_REDPANDA=true
while [ $# -gt 0 ]; do
  case "$1" in
    --no-kafka) WITH_REDPANDA=false ;;
    -h|--help)  print_help; exit 0 ;;
    *) print_help >&2; exit 2 ;;
  esac
  shift
done

require_env
require_docker
for key in KAFKA_BOOTSTRAP_SERVERS KAFKA_TOPIC_1 INFLUXDB_ORG INFLUXDB_BUCKET \
           INFLUXDB_ADMIN_PASSWORD INFLUXDB_TOKEN GRAFANA_ADMIN_PASSWORD; do
  env_value "$ENV_FILE" "$key" >/dev/null
done

profiles=()
if [ "$WITH_REDPANDA" = true ]; then
  profiles=(--profile redpanda)
  export KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
  echo "Building the consumer and starting InfluxDB, Grafana, the consumer and Redpanda..."
else
  echo "Building the consumer and starting InfluxDB, Grafana and the consumer..."
fi
compose "${profiles[@]}" up -d --build
wait_for_http "$GRAFANA_URL/api/health" \
  || { echo "Grafana did not answer on $GRAFANA_URL; see ./scripts/docker-helper.sh --logs" >&2
       exit 1; }

echo
echo "Grafana:   $GRAFANA_URL  (user admin, password GRAFANA_ADMIN_PASSWORD of .env)"
echo "InfluxDB:  http://localhost:8086  (user admin, password INFLUXDB_ADMIN_PASSWORD of .env)"
if [ "$WITH_REDPANDA" = true ]; then
  echo "Redpanda:  localhost:9092 (Kafka API), console at http://localhost:8080"
fi
echo "Publish this machine's container stats:  ./scripts/collect-stats.sh"
