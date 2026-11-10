#!/usr/bin/env bash
#
# Publish this machine's docker stats to a Kafka topic, one message per cycle, until stopped.
#
#   ./scripts/collect-stats.sh [--topic NAME] [--interval SECONDS] [--host NAME]
#
#   --topic NAME        the topic to publish to (default: KAFKA_TOPIC_1 of .env)
#   --interval SECONDS  the pause between two messages (default: 10)
#   --host NAME         the name the dashboard shows for this machine (default: its hostname)
#   -h, --help
#
#   ./scripts/collect-stats.sh
#   ./scripts/collect-stats.sh --host laptop --interval 5
#
# A message is {"timestamp": ..., "host": ..., "stats": [one docker stats row per container]}.
# The broker is KAFKA_BOOTSTRAP_SERVERS of .env. Requires docker and jq, and uses the first
# producer it finds: rpk, kcat, kafkacat, rpk inside a running "redpanda" container, or a
# cp-kafka container started for every message. The last one costs a JVM start per cycle and
# cannot reach a broker addressed as localhost, so install rpk or kcat where it would be used.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

# A container younger than this is left out: its stats are still zero or noise.
SETTLE_SECONDS=5

TOPIC=""
INTERVAL=10
HOST_NAME="$(hostname)"
while [ $# -gt 0 ]; do
  case "$1" in
    --topic|--interval|--host)
      [ $# -ge 2 ] || { print_help >&2; exit 2; }
      case "$1" in
        --topic)    TOPIC="$2" ;;
        --interval) INTERVAL="$2" ;;
        --host)     HOST_NAME="$2" ;;
      esac
      shift ;;
    -h|--help) print_help; exit 0 ;;
    *) print_help >&2; exit 2 ;;
  esac
  shift
done

[[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]] \
  || { echo "--interval takes a whole number of seconds, got '$INTERVAL'" >&2; exit 2; }
[ -n "$HOST_NAME" ] || { echo "--host takes a non-empty name" >&2; exit 2; }
require_env
require_docker
require_command jq
BROKER="$(env_value "$ENV_FILE" KAFKA_BOOTSTRAP_SERVERS)"
[ -n "$TOPIC" ] || TOPIC="$(env_value "$ENV_FILE" KAFKA_TOPIC_1)"

if command -v rpk >/dev/null 2>&1; then
  PRODUCER="rpk"
elif command -v kcat >/dev/null 2>&1; then
  PRODUCER="kcat"
elif command -v kafkacat >/dev/null 2>&1; then
  PRODUCER="kafkacat"
elif docker ps --format '{{.Names}}' | grep -qx redpanda; then
  PRODUCER="rpk in the redpanda container"
else
  PRODUCER="cp-kafka container"
fi

publish() {  # message
  case "$PRODUCER" in
    rpk)      printf '%s\n' "$1" | rpk topic produce "$TOPIC" -X brokers="$BROKER" >/dev/null ;;
    kcat)     printf '%s\n' "$1" | kcat -P -b "$BROKER" -t "$TOPIC" ;;
    kafkacat) printf '%s\n' "$1" | kafkacat -P -b "$BROKER" -t "$TOPIC" ;;
    "rpk in the redpanda container")
      # Inside its own container the broker listens on localhost:9092, whatever address this
      # machine reaches it by.
      printf '%s\n' "$1" \
        | docker exec -i redpanda rpk topic produce "$TOPIC" -X brokers=localhost:9092 >/dev/null
      ;;
    "cp-kafka container")
      printf '%s\n' "$1" | docker run --rm -i confluentinc/cp-kafka:7.9.2 \
        kafka-console-producer --bootstrap-server "$BROKER" --topic "$TOPIC"
      ;;
  esac
}

# Prints the message for this moment. Fails when docker cannot be read, which includes a
# container removed between the listing and the reading.
read_message() {  # timestamp
  local ids id started now stats="[]"
  local -a settled=()
  ids="$(docker ps -q)" || return 1
  now="$(date -u +%s)"
  for id in $ids; do
    started="$(docker inspect --format '{{.State.StartedAt}}' "$id" 2>/dev/null)" || return 1
    if [ $(( now - $(date -d "$started" +%s) )) -ge "$SETTLE_SECONDS" ]; then
      settled+=("$id")
    fi
  done
  if [ ${#settled[@]} -gt 0 ]; then
    stats="$(docker stats --no-stream --format '{{json .}}' "${settled[@]}" | jq -s .)" \
      || return 1
  fi
  jq -nc --arg timestamp "$1" --arg host "$HOST_NAME" --argjson stats "$stats" \
    '{timestamp: $timestamp, host: $host, stats: $stats}'
}

echo "Publishing the docker stats of '$HOST_NAME' to topic '$TOPIC' on $BROKER every" \
     "${INTERVAL}s, through $PRODUCER. Ctrl+C stops."

# A cycle that fails costs its own reading and no more: the next message carries fresh figures,
# so the collector keeps running through a restarting docker or an absent broker and reports
# each miss.
while true; do
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if ! message="$(read_message "$timestamp")"; then
    echo "$timestamp  docker gave no reading; trying again in ${INTERVAL}s" >&2
  elif publish "$message"; then
    echo "$timestamp  published $(jq '.stats | length' <<<"$message") containers"
  else
    echo "$timestamp  publish failed; trying again in ${INTERVAL}s" >&2
  fi
  sleep "$INTERVAL"
done
