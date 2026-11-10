"""Tests for the conversion of a docker stats message into numbers."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from stats_message import (
    ContainerSample,
    MalformedMessage,
    parse_message,
    parse_percentage,
    parse_size,
    parse_size_pair,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0B", 0),
        ("512B", 512),
        ("1.5kB", 1_500),
        ("107MB", 107_000_000),
        ("2.5GB", 2_500_000_000),
        ("1TB", 1_000**4),
        ("1PB", 1_000**5),
        ("4KiB", 4_096),
        ("50.87MiB", 50.87 * 1024**2),
        ("1.803GiB", 1.803 * 1024**3),
        ("2TiB", 2 * 1024**4),
        ("1PiB", 1024**5),
        ("1e+03MiB", 1_000 * 1024**2),
        (" 38.4MB ", 38_400_000),
    ],
)
def test_parse_size_converts_every_unit_docker_prints(text: str, expected: float) -> None:
    assert parse_size(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "MiB", "12", "12XB", "12KB", "12 mib", "1.2.3MB", "-5MB"])
def test_parse_size_rejects_text_that_is_not_a_docker_size(text: str) -> None:
    with pytest.raises(MalformedMessage, match="size"):
        parse_size(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0.00%", 0.0), ("2.75%", 2.75), ("100%", 100.0), ("412.50%", 412.5), (" 7.1% ", 7.1)],
)
def test_parse_percentage(text: str, expected: float) -> None:
    assert parse_percentage(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "%", "2.75", "abc%", "2.75%%", "-1%"])
def test_parse_percentage_rejects_text_that_is_not_a_percentage(text: str) -> None:
    with pytest.raises(MalformedMessage, match="percentage"):
        parse_percentage(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("50.87MiB / 1.803GiB", (50.87 * 1024**2, 1.803 * 1024**3)),
        ("107MB / 766MB", (107e6, 766e6)),
        ("0B / 0B", (0, 0)),
        ("1.5kB/2kB", (1_500, 2_000)),
    ],
)
def test_parse_size_pair(text: str, expected: tuple[float, float]) -> None:
    assert parse_size_pair(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "107MB", "107MB / ", "1MB / 2MB / 3MB", "107MB - 766MB"])
def test_parse_size_pair_rejects_anything_but_two_sizes(text: str) -> None:
    with pytest.raises(MalformedMessage):
        parse_size_pair(text)


def container(**changes: Any) -> dict[str, Any]:
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
    entry.update(changes)
    return entry


def message(**changes: Any) -> dict[str, Any]:
    body = {"timestamp": "2026-11-10T18:11:05Z", "host": "ecs-kafka", "stats": [container()]}
    body.update(changes)
    return body


def encode(body: Any) -> bytes:
    return json.dumps(body).encode()


def without(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in mapping.items() if name != key}


def test_parse_message_reads_host_timestamp_and_every_container_field() -> None:
    snapshot = parse_message(encode(message()))

    assert snapshot.host == "ecs-kafka"
    assert snapshot.timestamp == datetime(2026, 11, 10, 18, 11, 5, tzinfo=UTC)
    assert snapshot.samples == (
        ContainerSample(
            container_id="3f2a9c1d7b6e",
            container_name="influxdb",
            cpu_percent=2.75,
            mem_used_bytes=50.87 * 1024**2,
            mem_limit_bytes=1.803 * 1024**3,
            mem_percent=2.76,
            net_rx_bytes=107e6,
            net_tx_bytes=766e6,
            block_read_bytes=38.4e6,
            block_write_bytes=810e6,
            pids=14,
        ),
    )


def test_parse_message_accepts_a_host_that_runs_no_containers() -> None:
    assert parse_message(encode(message(stats=[]))).samples == ()


def test_parse_message_leaves_out_a_container_docker_had_no_reading_for() -> None:
    stopped = container(
        Name="exited",
        CPUPerc="--",
        MemUsage="-- / --",
        MemPerc="--",
        NetIO="--",
        BlockIO="--",
        PIDs="--",
    )

    snapshot = parse_message(encode(message(stats=[stopped, container()])))

    assert [sample.container_name for sample in snapshot.samples] == ["influxdb"]


@pytest.mark.parametrize(
    ("raw", "names"),
    [
        (None, "no value"),
        (b"\xff\xfe", "UTF-8"),
        (b"{not json", "JSON"),
        (encode([1, 2]), "object"),
        (encode(without(message(), "host")), "host"),
        (encode(message(host="")), "host"),
        (encode(message(host=7)), "host"),
        (encode(without(message(), "timestamp")), "timestamp"),
        (encode(message(timestamp="yesterday")), "timestamp"),
        (encode(message(timestamp="2026-11-10T18:11:05")), "UTC offset"),
        (encode(without(message(), "stats")), "stats"),
        (encode(message(stats={"Name": "x"})), "stats"),
        (encode(message(stats=["influxdb"])), "stats"),
        (encode(message(stats=[without(container(), "MemUsage")])), "MemUsage"),
        (encode(message(stats=[container(CPUPerc=2.75)])), "CPUPerc"),
        (encode(message(stats=[container(MemUsage="50.87XiB / 1GiB")])), "50.87XiB"),
        (encode(message(stats=[container(NetIO="107MB")])), "107MB"),
        (encode(message(stats=[container(PIDs="many")])), "PIDs"),
    ],
)
def test_parse_message_names_the_part_that_breaks_the_contract(
    raw: bytes | None, names: str
) -> None:
    with pytest.raises(MalformedMessage, match=names):
        parse_message(raw)
