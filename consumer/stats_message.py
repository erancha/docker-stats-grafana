"""
The message a monitored host publishes each cycle, converted from docker's text into numbers.

A message is a JSON object with the host's name, a UTC timestamp and one entry per running
container, each entry holding the columns of docker stats as docker prints them
("50.87MiB / 1.803GiB", "2.75%").

Building blocks:
- parse_message turns the raw bytes into a HostSnapshot of ContainerSample values
- parse_size, parse_percentage and parse_size_pair convert one docker column each
- MalformedMessage is raised for any message that breaks this contract, naming the broken part
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# What docker prints in every numeric column of a container that stopped between the listing and
# the sampling.
NO_READING = "--"

# Bytes per unit. Docker prints memory in binary units and network and block I/O in decimal ones.
_UNIT_BYTES = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
    "PiB": 1024**5,
}

# Docker prints four significant digits, so a value that rounds up to 1000 arrives in exponent
# form ("1e+03MiB").
_SIZE = re.compile(r"(\d+(?:\.\d+)?(?:e[+-]\d+)?)\s*([A-Za-z]+)")
_PERCENTAGE = re.compile(r"(\d+(?:\.\d+)?)%")


class MalformedMessage(ValueError):
    """A message that breaks the producer contract; the text names the part that does."""


@dataclass(frozen=True)
class ContainerSample:
    """One container's row of docker stats, sizes in bytes and percentages as plain numbers."""

    container_id: str
    container_name: str
    cpu_percent: float
    mem_used_bytes: float
    mem_limit_bytes: float
    mem_percent: float
    net_rx_bytes: float
    net_tx_bytes: float
    block_read_bytes: float
    block_write_bytes: float
    pids: int


@dataclass(frozen=True)
class HostSnapshot:
    """The containers of one host at one moment. The timestamp always carries a UTC offset."""

    host: str
    timestamp: datetime
    samples: tuple[ContainerSample, ...]


def parse_size(text: str) -> float:
    """The number of bytes in a docker size such as '50.87MiB'."""
    match = _SIZE.fullmatch(text.strip())
    if match is None:
        raise MalformedMessage(f"{text!r} is not a size")
    value, unit = match.groups()
    if unit not in _UNIT_BYTES:
        raise MalformedMessage(f"{text!r} is a size in the unknown unit {unit!r}")
    return float(value) * _UNIT_BYTES[unit]


def parse_percentage(text: str) -> float:
    """The number in a docker percentage such as '2.75%'."""
    match = _PERCENTAGE.fullmatch(text.strip())
    if match is None:
        raise MalformedMessage(f"{text!r} is not a percentage")
    return float(match.group(1))


def parse_size_pair(text: str) -> tuple[float, float]:
    """Both sizes, in bytes, of a docker column such as '107MB / 766MB'."""
    parts = text.split("/")
    if len(parts) != 2:
        raise MalformedMessage(f"{text!r} is not two sizes separated by a slash")
    return parse_size(parts[0]), parse_size(parts[1])


def _parse_count(text: str) -> int:
    if not text.isascii() or not text.isdigit():
        raise MalformedMessage(f"{text!r} is not a count")
    return int(text)


def _text(mapping: dict[str, Any], key: str) -> str:
    if key not in mapping:
        raise MalformedMessage(f"{key} is missing")
    value = mapping[key]
    if not isinstance(value, str) or not value:
        raise MalformedMessage(f"{key} must be non-empty text, got {value!r}")
    return value


def _column[T](entry: dict[str, Any], key: str, parse: Callable[[str], T]) -> T:
    text = _text(entry, key)
    try:
        return parse(text)
    except MalformedMessage as error:
        raise MalformedMessage(f"{key}: {error}") from error


def _parse_sample(entry: dict[str, Any]) -> ContainerSample:
    mem_used, mem_limit = _column(entry, "MemUsage", parse_size_pair)
    net_rx, net_tx = _column(entry, "NetIO", parse_size_pair)
    block_read, block_write = _column(entry, "BlockIO", parse_size_pair)
    return ContainerSample(
        container_id=_text(entry, "Container"),
        container_name=_text(entry, "Name"),
        cpu_percent=_column(entry, "CPUPerc", parse_percentage),
        mem_used_bytes=mem_used,
        mem_limit_bytes=mem_limit,
        mem_percent=_column(entry, "MemPerc", parse_percentage),
        net_rx_bytes=net_rx,
        net_tx_bytes=net_tx,
        block_read_bytes=block_read,
        block_write_bytes=block_write,
        pids=_column(entry, "PIDs", _parse_count),
    )


def _parse_timestamp(text: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError as error:
        raise MalformedMessage(f"timestamp {text!r} is not an ISO 8601 time") from error
    if timestamp.tzinfo is None:
        raise MalformedMessage(f"timestamp {text!r} has no UTC offset")
    return timestamp


def parse_message(raw: bytes | None) -> HostSnapshot:
    """The snapshot a raw message carries. A container without a reading is left out.

    A Kafka record may have no value at all, which arrives here as None.
    """
    if raw is None:
        raise MalformedMessage("the message has no value")
    try:
        body = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise MalformedMessage(f"the message is not UTF-8: {error}") from error
    except json.JSONDecodeError as error:
        raise MalformedMessage(f"the message is not JSON: {error}") from error
    if not isinstance(body, dict):
        raise MalformedMessage(f"the message must be a JSON object, got {type(body).__name__}")

    host = _text(body, "host")
    timestamp = _parse_timestamp(_text(body, "timestamp"))
    if "stats" not in body:
        raise MalformedMessage("stats is missing")
    stats = body["stats"]
    if not isinstance(stats, list) or not all(isinstance(entry, dict) for entry in stats):
        raise MalformedMessage("stats must be a list of container entries")

    samples = tuple(
        _parse_sample(entry) for entry in stats if _text(entry, "CPUPerc") != NO_READING
    )
    return HostSnapshot(host=host, timestamp=timestamp, samples=samples)
