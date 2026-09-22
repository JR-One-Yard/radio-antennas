from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

TREND_FIELDS = (
    "temperature_C",
    "humidity",
    "pressure_kPa",
    "rain_mm",
    "wind_avg_m_s",
    "wind_max_m_s",
    "power_W",
)
QUIET_CATEGORIES = {"unmatched-pulse", "noise"}


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass
class Census:
    """Latest state per heard identity, a short live tape, and an hour of digest."""

    max_events: int = 400
    trend_points: int = 180
    digest_seconds: int = 3600
    events: deque[dict[str, Any]] = field(default_factory=deque)
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    hearings: deque[tuple[float, str]] = field(default_factory=deque)
    decoded: int = 0
    pulses: int = 0
    noise: int = 0
    repeats: int = 0
    companions: int = 0
    malformed: int = 0

    def ingest(self, sighting: dict[str, Any] | None) -> dict[str, Any] | None:
        """Fold one sighting in. Returns the public entity it touched (or None)."""
        if not sighting:
            self.malformed += 1
            return None
        if sighting.get("duplicate_of"):
            return self._absorb_repeat(sighting)
        if sighting.get("companion_of"):
            return self._absorb_companion(sighting)

        category = str(sighting.get("category") or "unknown")
        if sighting.get("kind") == "pulse":
            if category == "noise":
                self.noise += 1
            else:
                self.pulses += 1
        else:
            self.decoded += 1
        self.events.append(sighting)
        while len(self.events) > self.max_events:
            self.events.popleft()

        key = str(sighting.get("entity_key") or "")
        heard = _parse_time(sighting.get("time"))
        previous = self.entities.get(key)
        entity = previous or {
            "entity_key": key,
            "first_heard": sighting.get("time"),
            "count": 0,
            "repeats": 0,
            "companions": 0,
            "companion": None,
            "_times": deque(maxlen=24),
            "_trend": deque(maxlen=self.trend_points),
        }
        entity.update(
            {
                "kind": sighting.get("kind"),
                "category": category,
                "name": sighting.get("name"),
                "summary": sighting.get("summary"),
                "guess": sighting.get("guess"),
                "confidence": sighting.get("confidence"),
                "why": sighting.get("why"),
                "model": sighting.get("model"),
                "device_id": sighting.get("device_id"),
                "protocol": sighting.get("protocol"),
                "last_heard": sighting.get("time"),
                "count": int(entity["count"]) + 1,
                "rssi": sighting.get("rssi"),
                "snr": sighting.get("snr"),
                "fields": sighting.get("fields") or {},
                "flex": sighting.get("flex"),
                "last_sighting": sighting,
                "_sort": heard.timestamp(),
            }
        )
        if sighting.get("companion"):
            entity["companion"] = sighting["companion"]
        entity["_times"].append(heard.timestamp())
        if sighting.get("kind") == "decoded":
            entity["cadence_s"] = _cadence(entity["_times"])
            point = _trend_point(heard, sighting.get("fields") or {})
            if point:
                entity["_trend"].append(point)
        self.entities[key] = entity
        self.hearings.append((heard.timestamp(), key))
        self._trim_hearings()
        return self.public(entity)

    def _absorb_repeat(self, sighting: dict[str, Any]) -> dict[str, Any] | None:
        self.repeats += 1
        entity = self.entities.get(str(sighting.get("duplicate_of") or ""))
        if entity is None:
            return None
        entity["repeats"] = int(entity.get("repeats", 0)) + 1
        return self.public(entity)

    def _absorb_companion(self, sighting: dict[str, Any]) -> dict[str, Any] | None:
        self.companions += 1
        entity = self.entities.get(str(sighting.get("companion_of") or ""))
        if entity is None:
            return None
        entity["companions"] = int(entity.get("companions", 0)) + 1
        entity["companion"] = {
            "time": sighting.get("time"),
            "rf_kind": sighting.get("rf_kind"),
            "modulation": sighting.get("modulation"),
            "pulse_count": sighting.get("pulse_count"),
            "width_ms": sighting.get("width_ms"),
            "rssi": sighting.get("rssi"),
            "snr": sighting.get("snr"),
            "flex": sighting.get("flex"),
            "view": sighting.get("view"),
        }
        return self.public(entity)

    def public(self, entity: dict[str, Any]) -> dict[str, Any]:
        body = {key: value for key, value in entity.items() if not str(key).startswith("_")}
        body["trend"] = list(entity.get("_trend") or ())
        body["stale"] = self._is_stale(entity)
        return body

    def snapshot(self) -> dict[str, Any]:
        roster = sorted(
            (self.public(entity) for entity in self.entities.values()),
            key=lambda item: item.get("last_heard") or "",
            reverse=True,
        )
        by_category: dict[str, int] = {}
        for entity in roster:
            category = str(entity.get("category") or "unknown")
            by_category[category] = by_category.get(category, 0) + 1
        return {
            "decoded": self.decoded,
            "pulses": self.pulses,
            "noise": self.noise,
            "repeats": self.repeats,
            "companions": self.companions,
            "malformed": self.malformed,
            "entity_count": len(roster),
            "quiet_count": sum(
                1 for entity in roster if entity.get("category") in QUIET_CATEGORIES
            ),
            "by_category": by_category,
            "entities": roster,
            "recent": list(self.events)[-80:],
            "digest": self.digest(),
        }

    def digest(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Who spoke in the last hour, how often, and what a weather station ranged over."""
        current = now or datetime.now(UTC)
        self._trim_hearings(current)
        since = current.timestamp() - self.digest_seconds
        counts: dict[str, int] = {}
        first: dict[str, float] = {}
        last: dict[str, float] = {}
        for stamp, key in self.hearings:
            if stamp < since:
                continue
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, stamp)
            last[key] = stamp
        items = []
        for key, count in counts.items():
            entity = self.entities.get(key)
            if entity is None:
                continue
            item = {
                "entity_key": key,
                "name": entity.get("name"),
                "category": entity.get("category"),
                "count": count,
                "first": _iso(first[key]),
                "last": _iso(last[key]),
                "summary": entity.get("summary"),
            }
            ranges = _ranges(entity.get("_trend") or (), since)
            if ranges:
                item["ranges"] = ranges
            items.append(item)
        items.sort(key=lambda item: (item["category"] in QUIET_CATEGORIES, -item["count"]))
        return {
            "window_s": self.digest_seconds,
            "since": _iso(since),
            "entities": items,
            "total": sum(counts.values()),
        }

    def stale_after(self, seconds: float) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        for entity in self.entities.values():
            heard = _parse_time(entity.get("last_heard"))
            entity["stale"] = heard < cutoff

    def _is_stale(self, entity: dict[str, Any], *, floor: float = 180.0) -> bool:
        heard = _parse_time(entity.get("last_heard"))
        cadence = entity.get("cadence_s")
        allowed = max(floor, 3.0 * float(cadence)) if cadence else floor
        return (datetime.now(UTC) - heard).total_seconds() > allowed

    def _trim_hearings(self, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now(UTC)).timestamp() - self.digest_seconds
        while self.hearings and self.hearings[0][0] < cutoff:
            self.hearings.popleft()


def _cadence(times: deque[float]) -> float | None:
    if len(times) < 3:
        return None
    gaps = [b - a for a, b in zip(list(times), list(times)[1:], strict=False) if b > a]
    if not gaps:
        return None
    return round(statistics.median(gaps), 1)


def _trend_point(heard: datetime, fields: dict[str, Any]) -> dict[str, Any] | None:
    point: dict[str, Any] = {}
    for key in TREND_FIELDS:
        value = fields.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            point[key] = value
    if not point:
        return None
    point["t"] = _iso(heard.timestamp())
    return point


def _ranges(trend: Any, since: float) -> dict[str, dict[str, float]]:
    ranges: dict[str, dict[str, float]] = {}
    for point in trend:
        stamp = _parse_time(point.get("t")).timestamp()
        if stamp < since:
            continue
        for key, value in point.items():
            if key == "t" or not isinstance(value, int | float):
                continue
            entry = ranges.setdefault(key, {"min": value, "max": value})
            entry["min"] = min(entry["min"], value)
            entry["max"] = max(entry["max"], value)
            entry["last"] = value
    return ranges


def _iso(stamp: float) -> str:
    return (
        datetime.fromtimestamp(stamp, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
