from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Observation:
    """One normalized, receive-only TPMS transmission."""

    sensor_id: str
    model: str
    observed_at: datetime
    received_at: datetime | None = None
    pressure_kpa: float | None = None
    temperature_c: float | None = None
    battery_ok: bool | None = None
    status: str | None = None
    rssi_db: float | None = None
    snr_db: float | None = None
    noise_db: float | None = None
    frequency_mhz: float | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.model.casefold(), self.sensor_id.casefold())

    @property
    def ordering_time(self) -> datetime:
        """Use the normalized effective observation time."""
        return ensure_utc(self.observed_at)

    def as_dict(
        self,
        *,
        now: datetime | None = None,
        stale_after_s: float | None = None,
    ) -> dict[str, Any]:
        reference = ensure_utc(now or datetime.now(UTC))
        observed_at = ensure_utc(self.observed_at)
        age_s = max(0.0, (reference - observed_at).total_seconds())
        stale = stale_after_s is not None and age_s >= stale_after_s
        return {
            "schema_version": 1,
            "sensor_id": self.sensor_id,
            "model": self.model,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "age_s": round(age_s, 3),
            "stale": stale,
            "pressure_kpa": self.pressure_kpa,
            "temperature_c": self.temperature_c,
            "battery_ok": self.battery_ok,
            "status": self.status,
            "rssi_db": self.rssi_db,
            "snr_db": self.snr_db,
            "noise_db": self.noise_db,
            "frequency_mhz": self.frequency_mhz,
        }


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    observation: Observation | None = None
    rejection: str | None = None

    def __post_init__(self) -> None:
        if (self.observation is None) == (self.rejection is None):
            raise ValueError("result must contain exactly one of observation or rejection")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
