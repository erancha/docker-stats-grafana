"""Tests for the consumer's settings, its InfluxDB points and its handling of each message."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from influxdb_client import Point

from consumer import Settings, consume, to_points
from stats_message import ContainerSample, HostSnapshot

ENVIRONMENT = {
    "KAFKA_BOOTSTRAP_SERVERS": "broker-1:9092,broker-2:9092",
    "KAFKA_TOPIC_1": "docker-stats-local",
    "KAFKA_TOPIC_2": "docker-stats-ecs-kafka",
    "KAFKA_GROUP_ID_SUFFIX": "-local",
    "INFLUXDB_URL": "http://influxdb:8086",
    "INFLUXDB_TOKEN": "token",
    "INFLUXDB_ORG": "org",
    "INFLUXDB_BUCKET": "bucket",
}


def test_settings_come_from_the_environment() -> None:
    settings = Settings.from_env(ENVIRONMENT)

    assert settings.bootstrap_servers == ["broker-1:9092", "broker-2:9092"]
    assert settings.topics == ["docker-stats-local", "docker-stats-ecs-kafka"]
    assert settings.group_id == "docker-stats-consumer-local"
    assert (settings.influxdb_url, settings.influxdb_token) == ("http://influxdb:8086", "token")
    assert (settings.influxdb_org, settings.influxdb_bucket) == ("org", "bucket")


@pytest.mark.parametrize("changes", [{"KAFKA_TOPIC_2": ""}, {"KAFKA_TOPIC_2": None}])
def test_the_second_topic_is_optional(changes: dict[str, str | None]) -> None:
    environment = {**ENVIRONMENT, **changes}
    present = {key: value for key, value in environment.items() if value is not None}

    assert Settings.from_env(present).topics == ["docker-stats-local"]


def test_the_group_id_suffix_is_optional() -> None:
    environment = {k: v for k, v in ENVIRONMENT.items() if k != "KAFKA_GROUP_ID_SUFFIX"}

    assert Settings.from_env(environment).group_id == "docker-stats-consumer"


@pytest.mark.parametrize(
    "key",
    [
        "KAFKA_BOOTSTRAP_SERVERS",
        "KAFKA_TOPIC_1",
        "INFLUXDB_URL",
        "INFLUXDB_TOKEN",
        "INFLUXDB_ORG",
        "INFLUXDB_BUCKET",
    ],
)
@pytest.mark.parametrize("state", ["absent", "blank"])
def test_a_required_setting_without_a_value_stops_the_start(key: str, state: str) -> None:
    environment = {k: v for k, v in ENVIRONMENT.items() if k != key}
    if state == "blank":
        environment[key] = ""

    with pytest.raises(RuntimeError, match=key):
        Settings.from_env(environment)


def test_each_container_becomes_one_point_tagged_with_its_host() -> None:
    snapshot = HostSnapshot(
        host="ecs-kafka",
        timestamp=datetime(2026, 11, 10, 18, 11, 5, tzinfo=UTC),
        samples=(
            ContainerSample(
                container_id="3f2a9c1d7b6e",
                container_name="influxdb",
                cpu_percent=2.75,
                mem_used_bytes=1024.0,
                mem_limit_bytes=2048.0,
                mem_percent=50.0,
                net_rx_bytes=10.0,
                net_tx_bytes=20.0,
                block_read_bytes=30.0,
                block_write_bytes=40.0,
                pids=14,
            ),
        ),
    )

    lines = [point.to_line_protocol() for point in to_points(snapshot)]

    assert lines == [
        "docker_stats,container_id=3f2a9c1d7b6e,container_name=influxdb,instance=ecs-kafka "
        "block_read_bytes=30,block_write_bytes=40,cpu_percent=2.75,mem_limit_bytes=2048,"
        "mem_percent=50,mem_used_bytes=1024,net_rx_bytes=10,net_tx_bytes=20,pids=14i "
        "1794334265000000000"
    ]


@dataclass
class Message:
    value: bytes
    topic: str = "docker-stats-local"
    partition: int = 0
    offset: int = 0


@dataclass
class FakeConsumer:
    """Yields the given messages and records how many were handed out before each commit."""

    messages: list[Message]
    handed_out: int = 0
    commits: list[int] = field(default_factory=list)

    def __iter__(self) -> Any:
        for message in self.messages:
            self.handed_out += 1
            yield message

    def commit(self) -> None:
        self.commits.append(self.handed_out)


def stats_message(host: str) -> bytes:
    entry = {
        "Container": "3f2a9c1d7b6e",
        "Name": "influxdb",
        "CPUPerc": "2.75%",
        "MemUsage": "50.87MiB / 1.803GiB",
        "MemPerc": "2.76%",
        "NetIO": "107MB / 766MB",
        "BlockIO": "38.4MB / 810MB",
        "PIDs": "14",
    }
    return json.dumps(
        {"timestamp": "2026-11-10T18:11:05Z", "host": host, "stats": [entry]}
    ).encode()


def test_a_malformed_message_is_counted_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    consumer = FakeConsumer(
        [
            Message(b"{not json", offset=7),
            Message(stats_message("host-a"), offset=8),
            Message(b"[]", offset=9),
        ]
    )
    written: list[list[Point]] = []

    with caplog.at_level(logging.ERROR):
        consume(consumer, written.append)

    assert [len(points) for points in written] == [1]
    assert consumer.commits == [1, 2, 3]
    rejections = [record.getMessage() for record in caplog.records]
    assert len(rejections) == 2
    assert "docker-stats-local[0]@7" in rejections[0] and "1 rejected" in rejections[0]
    assert "docker-stats-local[0]@9" in rejections[1] and "2 rejected" in rejections[1]


def test_a_host_without_containers_writes_nothing_and_is_committed() -> None:
    empty = json.dumps({"timestamp": "2026-11-10T18:11:05Z", "host": "host-a", "stats": []})
    consumer = FakeConsumer([Message(empty.encode())])
    written: list[list[Point]] = []

    consume(consumer, written.append)

    assert written == []
    assert consumer.commits == [1]


def test_a_failed_write_stops_the_consumer_before_the_message_is_committed() -> None:
    consumer = FakeConsumer([Message(stats_message("host-a")), Message(stats_message("host-b"))])

    def refuse(points: list[Point]) -> None:
        raise ConnectionError("InfluxDB is down")

    with pytest.raises(ConnectionError):
        consume(consumer, refuse)

    assert consumer.commits == []
