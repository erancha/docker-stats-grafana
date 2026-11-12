# 0003 — Hosts publish to a Kafka broker

- Status: Accepted
- Date: 2026-11-10

## Context

The containers to watch may run on several hosts, among them a deployed host that runs its own
broker and consumer. A host should not need to reach InfluxDB or Grafana, and a host whose
figures cannot be stored for a while should not lose them or stall. Each host already has
Docker, but not necessarily Python or a Kafka client.

## Decision

- Each host runs `scripts/collect-stats.sh`, a bash script that reads `docker stats` and
  publishes one JSON message per cycle to a Kafka topic.
- The script uses the first Kafka client it finds, down to a Kafka container started per
  message, so a host needs only Docker and `jq`.
- One consumer reads up to two topics and writes to InfluxDB; any Kafka-compatible broker
  serves, and the local stack runs Redpanda.

## Consequences

- A host needs network access to the broker alone.
- The broker holds messages while the consumer or InfluxDB is down, so their figures are stored
  when it returns, as long as the broker still retains them.
- The message is a contract between independent producers and the consumer, kept in
  [architecture.md](../architecture.md#the-message).
- The pipeline carries a broker, which is more to run than a direct write to InfluxDB.
