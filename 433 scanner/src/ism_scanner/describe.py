"""Turn a classified sighting into words a neighbour would use.

`name_for` is the stable roster label ("Garden weather · Cotech 53").
`summary_for` is the one-line current reading ("16.5 °C · 81 % RH · rain 318.6 mm").
"""

from __future__ import annotations

import re
from typing import Any

ROLE = {
    "weather": "Garden weather",
    "tpms": "Car tyre",
    "remote": "Remote",
    "security": "Alarm or sensor",
    "energy": "Energy monitor",
    "vehicle-key": "Car key",
    "utility": "Meter or utility",
    "unknown": "Unnamed device",
    "unmatched-pulse": "Unclaimed burst",
    "noise": "Noise floor",
}

_FLEX_PART = re.compile(r"(?P<key>[a-z]+)=(?P<value>[^,]+)")
_MOD_SHORT = {
    "OOK_PWM": "OOK PWM",
    "OOK_PPM": "OOK PPM",
    "OOK_MC_ZEROBIT": "OOK Manchester",
    "OOK_PCM": "OOK PCM",
    "OOK_DMC": "OOK DMC",
    "OOK_PIWM_RAW": "OOK PIWM",
    "OOK_PIWM_DC": "OOK PIWM",
    "FSK_PCM": "FSK PCM",
    "FSK_PWM": "FSK PWM",
    "FSK_MC_ZEROBIT": "FSK Manchester",
}


def parse_flex(flex: str | None) -> dict[str, Any]:
    """Split "n=name,m=OOK_PWM,s=495,l=975,r=5874" into a dict with numeric values."""
    if not flex:
        return {}
    parsed: dict[str, Any] = {}
    for match in _FLEX_PART.finditer(flex):
        key, value = match.group("key"), match.group("value").strip()
        try:
            parsed[key] = float(value) if "." in value else int(value)
        except ValueError:
            parsed[key] = value
    return parsed


def brand_of(model: str | None) -> str:
    """ "Cotech-367959" → "Cotech", "Hyundai-VDO" → "Hyundai VDO", "Fineoffset-WH51" stays."""
    if not model:
        return "Unknown"
    tokens = [token for token in re.split(r"[-_\s]+", model.strip()) if token]
    kept = [token for token in tokens if not (token.isdigit() and len(token) >= 4)]
    return " ".join(kept or tokens[:1])


def name_for(event: dict[str, Any]) -> str:
    category = str(event.get("category") or "unknown")
    if event.get("kind") == "pulse":
        return _pulse_name(event, category)
    role = ROLE.get(category, "Device")
    brand = brand_of(event.get("model"))
    device_id = event.get("device_id")
    channel = (event.get("fields") or {}).get("channel")
    label = f"{brand} {device_id}" if device_id else brand
    if channel not in (None, "") and category == "weather":
        label = f"{label} ch{channel}"
    return f"{role} · {label}"


def _pulse_name(event: dict[str, Any], category: str) -> str:
    kind = str(event.get("rf_kind") or "RF")
    if category == "noise":
        return "Noise floor"
    modulation = str(event.get("modulation") or "")
    if "No clue" in modulation:
        return f"Unrecognised {kind} chatter"
    hint = parse_flex(event.get("flex"))
    if hint.get("m"):
        short = _MOD_SHORT.get(str(hint["m"]), str(hint["m"]))
        if hint.get("s"):
            return f"Unclaimed burst · {short} ~{_round_us(hint['s'])} µs"
        return f"Unclaimed burst · {short}"
    return f"Unclaimed {kind} burst · {modulation or 'unknown timing'}"


def summary_for(event: dict[str, Any]) -> str:
    category = str(event.get("category") or "unknown")
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    if event.get("kind") == "pulse":
        return _pulse_summary(event, category)
    if category == "weather":
        return _weather_summary(fields)
    if category == "tpms":
        return _tpms_summary(fields)
    if category == "energy":
        return _energy_summary(fields)
    if category in {"remote", "vehicle-key", "security"}:
        return _event_summary(fields)
    return _generic_summary(fields)


def _pulse_summary(event: dict[str, Any], category: str) -> str:
    count = event.get("pulse_count")
    width = event.get("width_ms")
    rssi = event.get("rssi")
    parts = []
    if category == "noise":
        parts.append("single spike" if (count or 1) <= 1 else f"{int(count)}-pulse blip")
    elif count is not None:
        parts.append(f"{int(count)} pulses")
    if width is not None:
        parts.append(f"{_fmt(width, 1)} ms")
    if rssi is not None:
        parts.append(f"{_fmt(rssi, 1)} dB")
    return " · ".join(parts)


def _weather_summary(fields: dict[str, Any]) -> str:
    parts = []
    temp = _temperature_c(fields)
    if temp is not None:
        parts.append(f"{_fmt(temp, 1)} °C")
    if (humidity := _num(fields.get("humidity"))) is not None:
        parts.append(f"{_fmt(humidity, 0)} % RH")
    if (rain := _num(fields.get("rain_mm"))) is not None:
        parts.append(f"rain {_fmt(rain, 1)} mm")
    wind = _num(fields.get("wind_avg_m_s"))
    gust = _num(fields.get("wind_max_m_s"))
    direction = _num(fields.get("wind_dir_deg"))
    if wind is not None or gust is not None:
        text = f"wind {_fmt((wind if wind is not None else gust) * 3.6, 0)} km/h"
        if gust is not None and wind is not None and gust > wind:
            text += f" (gusts {_fmt(gust * 3.6, 0)})"
        if direction is not None:
            text += f" from {_compass(direction)}"
        parts.append(text)
    if (lux := _num(fields.get("light_lux"))) is not None and lux > 0:
        parts.append(f"{_fmt(lux, 0)} lx")
    if (uvi := _num(fields.get("uvi"))) is not None and uvi > 0:
        parts.append(f"UV {_fmt(uvi, 1)}")
    if (moisture := _num(fields.get("moisture"))) is not None:
        parts.append(f"soil {_fmt(moisture, 0)} %")
    battery = _battery(fields)
    if battery is False:
        parts.append("battery low")
    return " · ".join(parts) or _generic_summary(fields)


def _tpms_summary(fields: dict[str, Any]) -> str:
    parts = []
    kpa = _num(fields.get("pressure_kPa"))
    if kpa is not None:
        parts.append(f"{_fmt(kpa, 0)} kPa ({_fmt(kpa / 6.894757, 1)} psi)")
    temp = _temperature_c(fields)
    if temp is not None:
        parts.append(f"{_fmt(temp, 0)} °C")
    battery = _battery(fields)
    if battery is True:
        parts.append("battery ok")
    elif battery is False:
        parts.append("battery low")
    return " · ".join(parts) or "tyre sensor woke, no readings decoded"


def _energy_summary(fields: dict[str, Any]) -> str:
    parts = []
    if (power := _num(fields.get("power_W"))) is not None:
        parts.append(f"{_fmt(power, 0)} W")
    if (energy := _num(fields.get("energy_kWh"))) is not None:
        parts.append(f"{_fmt(energy, 1)} kWh")
    if (current := _num(fields.get("current_A"))) is not None:
        parts.append(f"{_fmt(current, 1)} A")
    return " · ".join(parts) or _generic_summary(fields)


def _event_summary(fields: dict[str, Any]) -> str:
    parts = []
    for key in ("cmd", "command", "button", "code", "state", "event", "status"):
        value = fields.get(key)
        if value not in (None, ""):
            parts.append(f"{key} {value}")
    if fields.get("channel") not in (None, ""):
        parts.append(f"channel {fields['channel']}")
    if _battery(fields) is False:
        parts.append("battery low")
    return " · ".join(parts[:4]) or _generic_summary(fields)


def _generic_summary(fields: dict[str, Any]) -> str:
    skip = {"id", "mod", "mic", "type", "protocol", "raw", "freq1", "freq2", "repeat"}
    parts = [
        f"{key} {value}"
        for key, value in fields.items()
        if key not in skip and value not in (None, "") and not str(key).startswith("_")
    ]
    return " · ".join(parts[:4])


def _temperature_c(fields: dict[str, Any]) -> float | None:
    celsius = _num(fields.get("temperature_C"))
    if celsius is not None:
        return celsius
    fahrenheit = _num(fields.get("temperature_F"))
    if fahrenheit is not None:
        return (fahrenheit - 32) * 5 / 9
    return None


def _battery(fields: dict[str, Any]) -> bool | None:
    value = fields.get("battery_ok", fields.get("battery"))
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"ok", "1", "true", "good", "normal"}:
            return True
        if low in {"low", "0", "false", "bad", "replace"}:
            return False
    return None


def _compass(degrees: float) -> str:
    points = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return points[int((degrees % 360 + 22.5) // 45) % 8]


def _round_us(value: Any) -> int:
    number = _num(value) or 0
    step = 5 if number < 200 else 10 if number < 2000 else 100
    return int(round(number / step) * step)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float, digits: int) -> str:
    text = f"{value:.{digits}f}"
    return text if digits else str(int(round(value)))
