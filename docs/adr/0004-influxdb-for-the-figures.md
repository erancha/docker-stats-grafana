# 0004 — InfluxDB stores the figures

- Status: Accepted
- Date: 2026-11-10

## Context

Each message holds one host's reading for one moment, and the dashboard draws the last
minutes per container and per host. The figures are queried by time and filtered by host and
container; they are never updated, and the dashboard looks at minutes and hours, not months.

## Decision

- InfluxDB 2.7 holds one `docker_stats` point per container per message, at the message's
  timestamp, tagged with the host, the container id and the container name.
- The bucket keeps points for 30 days.
- Grafana reads the bucket through Flux queries.

## Consequences

- A point written twice has the same tags and timestamp, so it replaces the first; this makes a
  repeated delivery harmless ([ADR 0001](0001-commit-after-write.md)).
- The network and disk fields are docker's running totals, and the dashboard draws their rate
  of change.
- The volume stays bounded on a small host's disk.
- InfluxDB applies its organization, bucket, token and admin password only when its volume is
  first created, so changing them later means deleting the stored points.
