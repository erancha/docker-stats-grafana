# 0002 — The message names its host

- Status: Accepted
- Date: 2026-11-10

## Context

The consumer derived the `instance` tag from the topic: the last two dash-separated parts of
its name. The topic `docker-stats-ecs-kafka` gave `ecs-kafka`, but the default topic
`docker-stats-local` gave `stats-local`, and two hosts publishing to one topic were stored as
one. The producer knows which machine it runs on; the topic name is a routing choice.

## Decision

Each message carries a required `host` field, which the consumer writes as the `instance` tag.
`collect-stats.sh` fills it with the machine's hostname, or with `--host NAME`. A message
without `host` is malformed.

## Consequences

- Any number of hosts can share a topic, and a topic can be renamed without renaming a series.
- The tag keeps the name `instance`, so points stored earlier and the dashboard's Host
  selector keep working.
- Every producer must send `host`. A producer written to the earlier message has all its
  messages rejected until it is updated.
