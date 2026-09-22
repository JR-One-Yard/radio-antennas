from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any

from ism_scanner.classify import Classification, classify
from ism_scanner.describe import name_for, parse_flex, summary_for

_JSON_START = re.compile(r"^\s*\{")
_PACKAGE = re.compile(
    r"^Detected\s+(?P<kind>OOK|FSK)\s+package(?:\s+(?P<time>\S+))?",
    re.IGNORECASE,
)
_TOTAL = re.compile(
    r"^Total count:\s*(?P<count>\d+),\s*width:\s*(?P<width>[\d.]+)\s*ms",
    re.IGNORECASE,
)
_RSSI = re.compile(
    r"^RSSI:\s*(?P<rssi>-?[\d.]+)\s*dB\s+SNR:\s*(?P<snr>-?[\d.]+)\s*dB\s+Noise:\s*(?P<noise>-?[\d.]+)\s*dB",
    re.IGNORECASE,
)
_MODULATION = re.compile(r"^Guessing modulation:\s*(?P<mod>.+)$", re.IGNORECASE)
_VIEW = re.compile(r"^view at\s+(?P<url>\S+)", re.IGNORECASE)
_FLEX = re.compile(r"Use a flex decoder with -X '(?P<flex>[^']+)'")
_DEMOD = re.compile(r"^Attempting demodulation\.\.\.\s*(?P<rest>.*)$", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

KEEP_FIELDS = (
    "id",
    "type",
    "channel",
    "battery_ok",
    "battery",
    "status",
    "temperature_C",
    "temperature_F",
    "humidity",
    "pressure_kPa",
    "pressure_PSI",
    "rain_mm",
    "wind_dir_deg",
    "wind_avg_m_s",
    "wind_max_m_s",
    "light_lux",
    "uvi",
    "moisture",
    "button",
    "cmd",
    "command",
    "code",
    "state",
    "mod",
    "mic",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sighting_from_decoded(
    payload: dict[str, Any], *, heard_at: str | None = None
) -> dict[str, Any]:
    fields = {
        key: payload[key]
        for key in KEEP_FIELDS
        if key in payload and payload[key] not in (None, "")
    }
    extras = {
        key: value
        for key, value in payload.items()
        if key not in fields
        and key
        not in {
            "time",
            "model",
            "protocol",
            "freq",
            "frequency",
            "rssi",
            "snr",
            "noise",
        }
        and not str(key).startswith("_")
    }
    fields.update(extras)
    _derive_units(fields)
    event = {
        "kind": "decoded",
        "time": _time(payload.get("time"), heard_at),
        "model": _text(payload.get("model")),
        "device_id": _identity(payload.get("id"))
        or _identity(payload.get("sensor_id"))
        or _identity(payload.get("sid")),
        "protocol": payload.get("protocol"),
        "frequency_hz": _frequency_hz(payload),
        "rssi": _number(payload.get("rssi")),
        "snr": _number(payload.get("snr")),
        "noise": _number(payload.get("noise")),
        "modulation": _text(payload.get("mod")),
        "fields": fields,
        "raw": payload,
    }
    return _with_classification(event)


def sighting_from_pulse(pulse: dict[str, Any]) -> dict[str, Any]:
    event = {
        "kind": "pulse",
        "time": _time(pulse.get("time"), None),
        "model": None,
        "device_id": None,
        "protocol": None,
        "frequency_hz": None,
        "rssi": _number(pulse.get("rssi")),
        "snr": _number(pulse.get("snr")),
        "noise": _number(pulse.get("noise")),
        "modulation": pulse.get("modulation"),
        "rf_kind": pulse.get("rf_kind"),
        "pulse_count": pulse.get("pulse_count"),
        "width_ms": pulse.get("width_ms"),
        "flex": pulse.get("flex"),
        "flex_hint": parse_flex(pulse.get("flex")),
        "view": pulse.get("view"),
        "demod_attempted": pulse.get("demod_attempted", False),
        "demod_failed": pulse.get("demod_failed", False),
        "fields": {
            key: value
            for key, value in pulse.items()
            if key not in {"raw_lines"} and value not in (None, "", [])
        },
        "raw": pulse,
    }
    return _with_classification(event)


def _with_classification(event: dict[str, Any]) -> dict[str, Any]:
    labelled: Classification = classify(event)
    event["category"] = labelled.category
    event["guess"] = labelled.guess
    event["confidence"] = round(labelled.confidence, 3)
    event["why"] = labelled.why
    event["entity_key"] = entity_key(event)
    event["name"] = name_for(event)
    event["summary"] = summary_for(event)
    return event


def entity_key(event: dict[str, Any]) -> str:
    """Stable identity. Pulses group by shape (not exact count) so noise does not
    mint a fresh identity for every burst."""
    if event.get("kind") == "pulse":
        return _pulse_key(event)
    model = _slug(str(event.get("model") or "unknown"))
    device_id = event.get("device_id")
    if device_id:
        return f"{model}:{device_id}"
    return f"{model}:anonymous"


def _pulse_key(event: dict[str, Any]) -> str:
    if event.get("category") == "noise":
        return "noise"
    kind = _slug(str(event.get("rf_kind") or "burst"))
    modulation = str(event.get("modulation") or "")
    if "No clue" in modulation:
        return f"pulse:{kind}:no-clue"
    hint = event.get("flex_hint") or parse_flex(event.get("flex"))
    if isinstance(hint, dict) and hint.get("m"):
        scheme = _slug(str(hint["m"]))
        short = hint.get("s")
        if isinstance(short, int | float) and short > 0:
            # Geometric buckets (~25 % wide) so 493 µs and 495 µs land together.
            return f"pulse:{kind}:{scheme}:s{int(round(math.log(short) / math.log(1.25)))}"
        return f"pulse:{kind}:{scheme}"
    return f"pulse:{kind}:{_slug(modulation or 'unknown')}"


_PRESSURE_TO_KPA = (
    ("pressure_kPa", 1.0),
    ("pressure_kpa", 1.0),
    ("pressure_PSI", 6.894757),
    ("pressure_psi", 6.894757),
    ("pressure_bar", 100.0),
)


def _derive_units(fields: dict[str, Any]) -> None:
    """Fill the metric fields the summaries rely on (Australia reads kPa and °C).

    Mirrors the TPMS sensor scanner's normaliser: pressure is folded to kPa from
    psi/bar, temperature to °C from °F. Original fields are kept alongside.
    """
    if _number(fields.get("pressure_kPa")) is None:
        for key, multiplier in _PRESSURE_TO_KPA:
            value = _number(fields.get(key))
            if value is not None and 0 <= value * multiplier <= 2000:
                fields["pressure_kPa"] = round(value * multiplier, 1)
                break
    if _number(fields.get("temperature_C")) is None:
        fahrenheit = _number(fields.get("temperature_F"))
        if fahrenheit is not None:
            fields["temperature_C"] = round((fahrenheit - 32) * 5 / 9, 1)
    if "battery_ok" not in fields and "low_battery" in fields:
        low = _number(fields.get("low_battery"))
        if low is not None:
            fields["battery_ok"] = 0 if low else 1


class PulseAssembler:
    """Fold rtl_433 analyser text (usually on stderr) into pulse events."""

    def __init__(self) -> None:
        self._block: dict[str, Any] | None = None
        self._lines: list[str] = []

    def feed(self, line: str) -> dict[str, Any] | None:
        text = _control_strip(line).strip()
        if not text:
            # rtl_433 ends every analyser block with a blank stderr line. "No clue"
            # blocks have no other terminator, so without this they only surface
            # when the *next* burst arrives (seen live: 16 s late, out of order).
            return self.flush() if self._block and self._block_has_body() else None
        match = _PACKAGE.match(text)
        if match:
            finished = self.flush()
            self._block = {
                "kind": "pulse",
                "rf_kind": match.group("kind").upper(),
                "time": match.group("time") or utc_now(),
            }
            self._lines = [text]
            return finished
        if self._block is None:
            return None
        self._lines.append(text)
        self._ingest(text)
        if text.startswith("Use a flex decoder"):
            return self.flush()
        if text.startswith("view at ") and "No clue" in str(self._block.get("modulation") or ""):
            return self.flush()
        return None

    def _block_has_body(self) -> bool:
        block = self._block or {}
        return block.get("pulse_count") is not None or bool(block.get("modulation"))

    def flush(self) -> dict[str, Any] | None:
        if self._block is None:
            return None
        block = dict(self._block)
        block["raw_lines"] = list(self._lines)
        self._block = None
        self._lines = []
        if block.get("pulse_count") is None and not block.get("modulation"):
            return None
        return sighting_from_pulse(block)

    def _ingest(self, text: str) -> None:
        assert self._block is not None
        if match := _TOTAL.match(text):
            self._block["pulse_count"] = int(match.group("count"))
            self._block["width_ms"] = float(match.group("width"))
        elif match := _RSSI.match(text):
            self._block["rssi"] = float(match.group("rssi"))
            self._block["snr"] = float(match.group("snr"))
            self._block["noise"] = float(match.group("noise"))
        elif match := _MODULATION.match(text):
            self._block["modulation"] = match.group("mod").strip()
        elif match := _VIEW.match(text):
            self._block["view"] = match.group("url")
        elif match := _FLEX.search(text):
            self._block["flex"] = match.group("flex")
        elif match := _DEMOD.match(text):
            rest = match.group("rest").strip().lower()
            self._block["demod_attempted"] = True
            self._block["demod_failed"] = rest in {"no", "failed"} or rest.startswith("no")


def interpret_line(
    line: str, assembler: PulseAssembler, *, from_stderr: bool
) -> list[dict[str, Any]]:
    text = _control_strip(line).strip()
    if not text:
        if from_stderr:
            event = assembler.feed("")
            return [event] if event else []
        return []
    if _JSON_START.match(text):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, dict):
            return [sighting_from_decoded(payload)]
        return []
    if from_stderr:
        event = assembler.feed(text)
        return [event] if event else []
    return []


def _time(value: object, fallback: str | None) -> str:
    text = _text(value)
    if text:
        if text.endswith("Z") or "+" in text[10:]:
            return text
        return f"{text}Z" if "T" in text else text
    return fallback or utc_now()


def _identity(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _frequency_hz(payload: dict[str, Any]) -> float | None:
    if "frequency" in payload:
        number = _number(payload["frequency"])
        if number is None:
            return None
        return number if number > 10_000 else number * 1_000_000
    freq = _number(payload.get("freq"))
    if freq is None:
        return None
    return freq * 1_000_000 if freq < 10_000 else freq


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "x"


def _control_strip(value: str) -> str:
    return _CONTROL.sub("", value)
