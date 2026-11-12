# 0006 — Grafana is provisioned from files

- Status: Accepted
- Date: 2026-11-10

## Context

The dashboard must look the same in the local stack and in a separate deployment that runs
its own Grafana. That deployment does not use this repository's compose file, and a dashboard
built by hand in one Grafana does not reach the other.

## Decision

- `grafana/provisioning/` holds the InfluxDB datasource, the dashboard provider and the
  dashboard as JSON; Grafana loads them at start and opens on the dashboard.
- The datasource reads the InfluxDB address, organization, bucket and token from Grafana's
  environment, and the queries use the datasource's default bucket, so no file names a bucket
  or a token.
- The other deployment downloads these files from the `main` branch.

## Consequences

- A dashboard change is a reviewed text diff that every deployment picks up.
- A Grafana container that loads the files must receive the InfluxDB variables the datasource reads.
- A change to the datasource's variables changes the contract with the other deployment.
