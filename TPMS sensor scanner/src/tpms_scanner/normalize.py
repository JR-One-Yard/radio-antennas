from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from tpms_scanner.models import NormalizationResult, Observation, ensure_utc

_ID_FIELDS = ("id", "sensor_id", "sid", "code")
_PRESSURE_FIELDS = (
    ("pressure_kPa", 1.0),
    ("pressure_kpa", 1.0),
    ("pressure_PSI", 6.8947572932),
    ("pressure_psi", 6.8947572932),
    ("pressure_bar", 100.0),
)


def normalize_line(
    line: str,
    *,
    received_at: datetime | None = None,
) -> NormalizationResult:
    if line == "\x00tpms-scanner:oversized-line":
        return NormalizationResult(rejection="oversized_line")
    if any(0xDC80 <= ord(char) <= 0xDCFF for char in line):
        return NormalizationResult(rejection="malformed_encoding")
    if not line.strip():
        return NormalizationResult(rejection="blank_line")
    try:
        event = json.loads(line)
    except (ValueError, RecursionError, UnicodeError):
        return NormalizationResult(rejection="malformed_json")
    if not isinstance(event, dict):
        return NormalizationResult(rejection="non_object_json")
    return normalize_event(event, received_at=received_at)


def normalize_event(
    event: Mapping[str, Any],
    *,
    received_at: datetime | None = None,
) -> NormalizationResult:
    model = _text(event.get("model"), max_length=128) or "Unknown TPMS"
    event_type = _text(event.get("type"))
    if not (
        (event_type is not None and event_type.casefold() == "tpms") or "tpms" in model.casefold()
    ):
        return NormalizationResult(rejection="non_tpms")

    sensor_id = _first_identifier(event)
    if sensor_id is None:
        return NormalizationResult(rejection="missing_sensor_id")

    received = ensure_utc(received_at or datetime.now(UTC))
    parsed_time = _parse_time(event.get("time"))
    observed_at = (
        received
        if parsed_time is None or parsed_time > received + timedelta(minutes=5)
        else parsed_time
    )
    pressure_kpa = _pressure_kpa(event)
    temperature_c = _number(event.get("temperature_C"))
    if temperature_c is None:
        temperature_c = _number(event.get("temperature_c"))
    if temperature_c is not None and not -100 <= temperature_c <= 250:
        temperature_c = None

    observation = Observation(
        sensor_id=sensor_id,
        model=model,
        observed_at=observed_at,
        received_at=received,
        pressure_kpa=pressure_kpa,
        temperature_c=temperature_c,
        battery_ok=_battery_ok(event),
        status=_text(event.get("status"), max_length=256)
        or _text(event.get("flags"), max_length=256),
        rssi_db=_first_number(event, "rssi", "rssi_db"),
        snr_db=_first_number(event, "snr", "snr_db"),
        noise_db=_first_number(event, "noise", "noise_db"),
        frequency_mhz=_frequency_mhz(event),
    )
    return NormalizationResult(observation=observation)


def _first_identifier(event: Mapping[str, Any]) -> str | None:
    for field in _ID_FIELDS:
        value = event.get(field)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (str, int)):
            text = str(value).strip()
            if text and len(text) <= 128:
                return text
    return None


def _pressure_kpa(event: Mapping[str, Any]) -> float | None:
    for field, multiplier in _PRESSURE_FIELDS:
        value = _number(event.get(field))
        if value is not None:
            converted = value * multiplier
            if math.isfinite(converted) and 0 <= converted <= 2000:
                return round(converted, 3)
    return None


def _battery_ok(event: Mapping[str, Any]) -> bool | None:
    if "battery_ok" in event:
        return _boolean(event.get("battery_ok"))
    if "battery" in event:
        return _boolean(event.get("battery"))
    if "low_battery" in event:
        low = _boolean(event.get("low_battery"))
        return None if low is None else not low
    return None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "ok", "good", "normal"}:
            return True
        if normalized in {"0", "false", "no", "low", "bad", "replace"}:
            return False
    return None


def _frequency_mhz(event: Mapping[str, Any]) -> float | None:
    value = _first_number(event, "frequency", "freq", "frequency_mhz")
    if value is None:
        return None
    if value > 100_000:
        value = round(value / 1_000_000, 6)
    return value if 0 < value <= 10_000 else None


def _first_number(event: Mapping[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = _number(event.get(field))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any, *, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_length] if max_length is not None else text


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            return ensure_utc(datetime.fromisoformat(candidate))
        except (ValueError, OverflowError):
            pass
    return None
