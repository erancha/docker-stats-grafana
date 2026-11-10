# 0001 — Commit a message after its points are stored

- Status: Accepted
- Date: 2026-11-10

## Context

The consumer let the Kafka client commit offsets on a timer and caught every error while
handling a message. A message whose write to InfluxDB failed was logged and lost, and so was a
message the consumer could not parse; neither was counted. The pipeline carries metrics: a
message is one host's reading for one moment, superseded 10 seconds later, and the dashboard
shows the last 15 minutes.

## Decision

The consumer commits each message itself, after handling it.

- A failed write is not handled: the exception ends the process before the commit, the
  container restarts, and the message is read again.
- A message that breaks the contract in [architecture.md](../architecture.md) is logged with
  its position and a running count, then committed.
- A consumer group without a committed offset starts at the newest message.

## Consequences

- Delivery to InfluxDB is at least once. A repeated point has the same measurement, tags and
  timestamp as the first, so it replaces it and no figure is counted twice.
- An InfluxDB outage shows as a restarting consumer, and the data of the outage is stored when
  InfluxDB returns, as long as the broker still retains it.
- A write InfluxDB will never accept is retried like an outage, so it blocks the topic until
  an operator intervenes. This is loud by design: skipping it would hide a schema conflict.
- A producer that sends malformed messages loses them. The count in the log is the only
  signal; there is no dead-letter topic.
- One commit per message costs a broker round trip each. At one message per host per cycle
  this is negligible; a far higher message rate would need batched commits.
