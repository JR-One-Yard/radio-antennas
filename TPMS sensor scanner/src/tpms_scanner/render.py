from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from tpms_scanner.models import Observation

_HEADERS = ("MODEL", "SENSOR ID", "PRESSURE", "TEMP", "BATTERY", "AGE", "STATE")


def json_line(
    observation: Observation,
    *,
    now: datetime | None = None,
    stale_after_s: float = 300.0,
) -> str:
    return json.dumps(
        observation.as_dict(now=now, stale_after_s=stale_after_s),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def format_table(
    observations: Iterable[Observation],
    *,
    now: datetime | None = None,
    stale_after_s: float = 300.0,
) -> str:
    reference = now or datetime.now(UTC)
    rows = [_row(observation, reference, stale_after_s) for observation in observations]
    if not rows:
        return "No TPMS sensors observed."

    widths = [
        max(len(_HEADERS[index]), *(len(row[index]) for row in rows))
        for index in range(len(_HEADERS))
    ]
    header = _format_row(_HEADERS, widths)
    divider = "-+-".join("-" * width for width in widths)
    body = "\n".join(_format_row(row, widths) for row in rows)
    return f"{header}\n{divider}\n{body}"


def _row(
    observation: Observation,
    now: datetime,
    stale_after_s: float,
) -> tuple[str, ...]:
    values = observation.as_dict(now=now, stale_after_s=stale_after_s)
    battery = "-"
    if observation.battery_ok is not None:
        battery = "OK" if observation.battery_ok else "LOW"
    state = "STALE" if values["stale"] else (observation.status or "CURRENT")
    return (
        _display_text(observation.model),
        _display_text(observation.sensor_id),
        _measurement(observation.pressure_kpa, "kPa", 1),
        _measurement(observation.temperature_c, "C", 1),
        battery,
        _age(float(values["age_s"])),
        _display_text(state),
    )


def _measurement(value: float | None, unit: str, decimals: int) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f} {unit}"


def _age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _format_row(row: Sequence[str], widths: Sequence[int]) -> str:
    return " | ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))


def _display_text(value: str, max_length: int = 40) -> str:
    safe = "".join("?" if unicodedata.category(char).startswith("C") else char for char in value)
    if len(safe) <= max_length:
        return safe
    return f"{safe[: max_length - 1]}…"
