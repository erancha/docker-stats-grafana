# 0005 — The stack runs in Docker Compose

- Status: Accepted
- Date: 2026-11-10

## Context

A developer needs InfluxDB, Grafana, the consumer and a broker on one machine, started and
stopped together, with the same settings each run. The machines involved already run Docker.
A broker or database reachable from the network would accept anyone, since the local broker
has no authentication.

## Decision

- `docker-compose.yml` runs InfluxDB, Grafana and the consumer, built from `consumer/`, plus a
  single-node Redpanda broker and its console under the profile `redpanda`.
- `.env` holds every setting; `scripts/init-env.sh` generates its credentials.
- Every port is published on the loopback interface only.
- Scripts under `scripts/` start, stop and inspect the stack.

## Consequences

- One command starts the stack, and `--no-kafka` leaves the broker out for one that runs
  elsewhere.
- The local broker serves only the machine it runs on; another host publishes to a broker it
  can reach.
- The container names are fixed, so two checkouts cannot run the stack at once.
