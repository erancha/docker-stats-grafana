# CLAUDE.md

A pipeline that shows every Docker container's stats in Grafana: a bash producer on each host
publishes to Kafka, a Python consumer writes to InfluxDB. The design is in
`docs/architecture.md`.

## Scripts

- `./scripts/test.sh`: bash syntax check of the scripts, then ruff, mypy and pytest for
  `consumer/` in `consumer/.venv`.
- `./scripts/init-env.sh`: create `.env` with generated credentials.
- `./scripts/start.sh [--no-kafka]`: build and start the Compose stack; returns once Grafana
  answers.
- `./scripts/docker-helper.sh --stop | --logs | --ps`: stop (volumes kept unless `--volumes`),
  logs, status.
- `./scripts/collect-stats.sh`: publish this machine's docker stats.
- `./scripts/build-push-consumer.sh`: build and push the consumer image.

## Facts that bite

- Other deployments use parts of this repository without its compose file: they download the
  three files under `grafana/provisioning/` from the `main` branch, run the consumer from the
  pushed image, and carry their own producer. A change to the datasource's variables, to the
  consumer's settings or to the message is a change to their contract; say so when making one.
- InfluxDB reads its credentials from `.env` only when its volume is first created.
- The container names (`influxdb`, `grafana`, `redpanda`) are fixed, so two checkouts cannot run
  the stack at once.
- `collect-stats.sh` falls back to `rpk` inside a container named `redpanda`; it detects it by
  that name.
