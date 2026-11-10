"""
Kafka consumer that stores each host's docker stats message as InfluxDB points.

Core responsibilities:
- Reads its settings from the environment and refuses to start when one is missing
- Writes one docker_stats point per container, tagged with the host that published it
- Commits a message's offset only after its points are stored, so a failed write is retried
- Counts and skips a message that breaks the producer contract, so one bad message cannot
  block the ones behind it
"""

import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from stats_message import HostSnapshot, MalformedMessage, parse_message

logger = logging.getLogger(__name__)

MEASUREMENT = "docker_stats"
GROUP_ID = "docker-stats-consumer"
CONNECT_ATTEMPTS = 30
CONNECT_RETRY_SECONDS = 2


@dataclass(frozen=True)
class Settings:
    """Where the consumer reads from and writes to. Every value comes from the environment."""

    bootstrap_servers: list[str]
    topics: list[str]
    group_id: str
    influxdb_url: str
    influxdb_token: str
    influxdb_org: str
    influxdb_bucket: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        def required(key: str) -> str:
            if not env.get(key):
                raise RuntimeError(f"{key} is not set; define it in .env (see .env.example)")
            return env[key]

        topics = [required("KAFKA_TOPIC_1")]
        if env.get("KAFKA_TOPIC_2"):
            topics.append(env["KAFKA_TOPIC_2"])
        # Two consumers that must each see every message, such as a developer's stack reading a
        # deployed broker beside the deployed consumer, set different suffixes.
        group_id = GROUP_ID
        if "KAFKA_GROUP_ID_SUFFIX" in env:
            group_id += env["KAFKA_GROUP_ID_SUFFIX"]
        return cls(
            bootstrap_servers=required("KAFKA_BOOTSTRAP_SERVERS").split(","),
            topics=topics,
            group_id=group_id,
            influxdb_url=required("INFLUXDB_URL"),
            influxdb_token=required("INFLUXDB_TOKEN"),
            influxdb_org=required("INFLUXDB_ORG"),
            influxdb_bucket=required("INFLUXDB_BUCKET"),
        )


class MessageSource(Protocol):
    """The part of KafkaConsumer the consumer loop uses."""

    def __iter__(self) -> Any: ...

    def commit(self) -> None: ...


def to_points(snapshot: HostSnapshot) -> list[Point]:
    return [
        Point(MEASUREMENT)
        .tag("instance", snapshot.host)
        .tag("container_id", sample.container_id)
        .tag("container_name", sample.container_name)
        .field("cpu_percent", sample.cpu_percent)
        .field("mem_used_bytes", sample.mem_used_bytes)
        .field("mem_limit_bytes", sample.mem_limit_bytes)
        .field("mem_percent", sample.mem_percent)
        .field("net_rx_bytes", sample.net_rx_bytes)
        .field("net_tx_bytes", sample.net_tx_bytes)
        .field("block_read_bytes", sample.block_read_bytes)
        .field("block_write_bytes", sample.block_write_bytes)
        .field("pids", sample.pids)
        .time(snapshot.timestamp)
        for sample in snapshot.samples
    ]


def consume(source: MessageSource, write: Callable[[list[Point]], None]) -> None:
    """Stores every message of the source, committing each one after it is stored or rejected.

    A write that fails raises out of the loop with the message uncommitted, so the restarted
    consumer reads it again; a point written twice overwrites itself.
    """
    rejected = 0
    for message in source:
        position = f"{message.topic}[{message.partition}]@{message.offset}"
        try:
            snapshot = parse_message(message.value)
        except MalformedMessage as error:
            rejected += 1
            logger.error("Rejected %s (%d rejected since start): %s", position, rejected, error)
        else:
            if snapshot.samples:
                write(to_points(snapshot))
            logger.info(
                "Stored %d containers of %s from %s", len(snapshot.samples), snapshot.host, position
            )
        source.commit()


def wait_for_influxdb(client: InfluxDBClient, url: str) -> None:
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        if client.ping():
            return
        logger.info("Waiting for InfluxDB at %s (%d/%d)", url, attempt, CONNECT_ATTEMPTS)
        time.sleep(CONNECT_RETRY_SECONDS)
    raise RuntimeError(f"InfluxDB at {url} did not answer")


def connect_to_kafka(settings: Settings) -> KafkaConsumer:
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return KafkaConsumer(
                *settings.topics,
                bootstrap_servers=settings.bootstrap_servers,
                group_id=settings.group_id,
                # A group without a committed offset starts at the present: the dashboard shows
                # recent minutes, so a backlog from before the group existed has no reader.
                auto_offset_reset="latest",
                enable_auto_commit=False,
            )
        except NoBrokersAvailable:
            logger.info(
                "Waiting for a Kafka broker at %s (%d/%d)",
                settings.bootstrap_servers,
                attempt,
                CONNECT_ATTEMPTS,
            )
            time.sleep(CONNECT_RETRY_SECONDS)
    raise RuntimeError(f"no Kafka broker answered at {settings.bootstrap_servers}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    settings = Settings.from_env(os.environ)
    logger.info(
        "Consuming %s from %s as %s into %s",
        settings.topics,
        settings.bootstrap_servers,
        settings.group_id,
        settings.influxdb_url,
    )

    with InfluxDBClient(
        url=settings.influxdb_url, token=settings.influxdb_token, org=settings.influxdb_org
    ) as influxdb:
        wait_for_influxdb(influxdb, settings.influxdb_url)
        write_api = influxdb.write_api(write_options=SYNCHRONOUS)
        source = connect_to_kafka(settings)
        try:
            consume(
                source,
                lambda points: write_api.write(
                    bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=points
                ),
            )
        finally:
            source.close()


if __name__ == "__main__":
    main()
