# Development

How to run, test and debug the stack, behind the Getting started section of the
[README](../README.md). The design is in [architecture.md](architecture.md).

**Contents:** [Local setup](#local-setup) · [Scripts](#scripts) · [Tests](#tests) ·
[A remote broker](#a-remote-broker) · [Gotchas](#gotchas) · [Troubleshooting](#troubleshooting)

## Local setup

Requires Docker with the Compose plugin (2.20 or newer), `jq`, `curl`, `openssl`, and Python
3.13 or newer for the tests.

```bash
./scripts/init-env.sh
./scripts/start.sh
./scripts/collect-stats.sh
```

Ports used on the machine, all published on the loopback interface only: 3100 (Grafana), 8086
(InfluxDB), and with the local broker 9092 (Kafka API), 8080 (Redpanda console), 18081, 18082
and 9644 (Redpanda's other APIs).

## Scripts

Each script's header is its documentation; `--help` prints it.

- [`init-env.sh`](../scripts/init-env.sh): create `.env`.
- [`start.sh`](../scripts/start.sh): build and start the stack.
- [`docker-helper.sh`](../scripts/docker-helper.sh): stop, logs, status.
- [`collect-stats.sh`](../scripts/collect-stats.sh): the producer.
- [`build-push-consumer.sh`](../scripts/build-push-consumer.sh): publish the consumer image.
- [`test.sh`](../scripts/test.sh): the quality gate.
- [`common.sh`](../scripts/common.sh): what the scripts share.

## Tests

`./scripts/test.sh` runs `bash -n` on the scripts, then ruff (lint and format check), mypy and
pytest in `consumer/`. It keeps a virtual environment in `consumer/.venv`, installed from
`requirements-dev.txt`, which includes the image's `requirements.txt`.

GitHub Actions runs the same script on every push and pull request.

The tests are table-driven: `tests/test_stats_message.py` lists docker's text forms with their
expected numbers and the malformed messages with the part each must name;
`tests/test_consumer.py` covers the settings, the points and the commit order of the loop.

## A remote broker

Set `KAFKA_BOOTSTRAP_SERVERS` in `.env` to an address that both this machine and the consumer
container can reach, and start with `./scripts/start.sh --no-kafka`. `localhost` does not work
there: inside the consumer container it means the container.

The consumer's group is `docker-stats-consumer-local`, so it reads every message beside a
deployed consumer in the group `docker-stats-consumer`.

## Gotchas

- InfluxDB applies its organization, bucket, retention period, admin password and token only
  when its volume is first created. A volume created under other values than `.env` holds,
  whether `.env` was edited or regenerated, leaves the consumer restarting on a 401 answer and
  Grafana without data. Run `./scripts/docker-helper.sh --stop --volumes` and start again; the
  stored points are lost.
- The pushed consumer image runs on one architecture, `linux/arm64` unless
  `build-push-consumer.sh --platform` says otherwise.
- A producer and a consumer must agree on the message. A producer that sends no `host` gets
  every message rejected; the consumer's log says so for each one.

## Troubleshooting

- **No data in the dashboard.** `./scripts/docker-helper.sh --logs kafka-to-influxdb`. A
  `Stored ...` line per message means data arrives: check the dashboard's time range and Host
  selector. `Rejected ...` lines name what is wrong with the messages. No lines mean nothing is
  published to the topics in `.env`: check that `collect-stats.sh` runs and which topic it
  prints.
- **The consumer keeps restarting.** Its log ends with the reason: a missing setting, a broker
  that does not answer, or a write that InfluxDB refused.
- **Redpanda does not start.** `./scripts/docker-helper.sh --logs redpanda`; check that its
  ports are free.
