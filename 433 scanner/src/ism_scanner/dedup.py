"""Fold the echoes rtl_433 produces for a single burst of RF.

Observed live on the NESDR (see docs/WORKAROUNDS.md):

* A weather packet is often decoded twice in the same second with identical
  fields and RSSI. The second is a *repeat*, not a new hearing.
* Every successful decode is followed by a pulse-analyser block for the same
  burst (same RSSI to 0.1 dB). That is a *companion*, not an unclaimed burst.

The deduper runs in the ingest thread before anything reaches the census. It
marks repeats with ``duplicate_of`` and companions with ``companion_of`` so the
census can count them against the real identity instead of minting rows.

Pulses arrive after the decode in rtl_433's own ordering, but the two are read
from different file descriptors, so a short *hold* keeps a pulse back for a few
hundred milliseconds in case its decode is still in flight.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_IGNORED_FOR_EQUALITY = {"rssi", "snr", "noise", "time", "freq", "freq1", "freq2", "repeat"}


class Deduper:
    def __init__(
        self,
        *,
        hold_seconds: float = 0.3,
        window_seconds: float = 1.5,
        time_tolerance: float = 1.0,
        rssi_tolerance: float = 0.6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hold_seconds = hold_seconds
        self.window_seconds = window_seconds
        self.time_tolerance = time_tolerance
        self.rssi_tolerance = rssi_tolerance
        self._clock = clock
        self._decodes: deque[tuple[float, dict[str, Any]]] = deque(maxlen=64)
        self._held: deque[tuple[float, dict[str, Any]]] = deque()
        self.repeats = 0
        self.companions = 0

    # -- public -----------------------------------------------------------

    def push(self, sighting: dict[str, Any]) -> list[dict[str, Any]]:
        """Return sightings ready to publish (may include released holds)."""
        now = self._clock()
        ready = self._release(now)
        if sighting.get("kind") == "pulse":
            ready.extend(self._push_pulse(sighting, now))
        else:
            ready.extend(self._push_decode(sighting, now))
        return ready

    def tick(self) -> list[dict[str, Any]]:
        return self._release(self._clock())

    def flush(self) -> list[dict[str, Any]]:
        ready = [pulse for _, pulse in self._held]
        self._held.clear()
        return ready

    # -- internals --------------------------------------------------------

    def _push_decode(self, decode: dict[str, Any], now: float) -> list[dict[str, Any]]:
        self._trim(now)
        for _, earlier in reversed(self._decodes):
            if self._is_repeat(earlier, decode):
                self.repeats += 1
                earlier["repeats"] = int(earlier.get("repeats", 0)) + 1
                decode["duplicate_of"] = earlier.get("entity_key")
                return [decode]
        # A companion pulse may have arrived first and be sitting in the hold.
        kept: deque[tuple[float, dict[str, Any]]] = deque()
        out: list[dict[str, Any]] = []
        for arrived, pulse in self._held:
            if self._is_companion(decode, pulse):
                self._claim(decode, pulse)
                out.append(pulse)
            else:
                kept.append((arrived, pulse))
        self._held = kept
        self._decodes.append((now, decode))
        return [decode, *out]

    def _push_pulse(self, pulse: dict[str, Any], now: float) -> list[dict[str, Any]]:
        self._trim(now)
        for _, decode in reversed(self._decodes):
            if self._is_companion(decode, pulse):
                self._claim(decode, pulse)
                return [pulse]
        if self.hold_seconds <= 0:
            return [pulse]
        self._held.append((now, pulse))
        return []

    def _release(self, now: float) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while self._held and now - self._held[0][0] >= self.hold_seconds:
            out.append(self._held.popleft()[1])
        return out

    def _trim(self, now: float) -> None:
        while self._decodes and now - self._decodes[0][0] > self.window_seconds:
            self._decodes.popleft()

    def _claim(self, decode: dict[str, Any], pulse: dict[str, Any]) -> None:
        self.companions += 1
        pulse["companion_of"] = decode.get("entity_key")
        decode["companion"] = _companion_summary(pulse)

    def _is_repeat(self, earlier: dict[str, Any], later: dict[str, Any]) -> bool:
        if earlier.get("entity_key") != later.get("entity_key"):
            return False
        if not _close(earlier.get("time"), later.get("time"), self.time_tolerance):
            return False
        return _payload(earlier) == _payload(later)

    def _is_companion(self, decode: dict[str, Any], pulse: dict[str, Any]) -> bool:
        rssi_a, rssi_b = decode.get("rssi"), pulse.get("rssi")
        if rssi_a is None or rssi_b is None:
            return False
        if abs(float(rssi_a) - float(rssi_b)) > self.rssi_tolerance:
            return False
        return _close(decode.get("time"), pulse.get("time"), self.time_tolerance)


def _companion_summary(pulse: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": pulse.get("time"),
        "rf_kind": pulse.get("rf_kind"),
        "modulation": pulse.get("modulation"),
        "pulse_count": pulse.get("pulse_count"),
        "width_ms": pulse.get("width_ms"),
        "rssi": pulse.get("rssi"),
        "snr": pulse.get("snr"),
        "flex": pulse.get("flex"),
        "view": pulse.get("view"),
    }


def _payload(sighting: dict[str, Any]) -> dict[str, Any]:
    fields = sighting.get("fields") or {}
    return {key: value for key, value in fields.items() if key not in _IGNORED_FOR_EQUALITY}


def _close(a: Any, b: Any, tolerance: float) -> bool:
    first, second = _epoch(a), _epoch(b)
    if first is None or second is None:
        return True  # no usable timestamps: trust arrival order and RSSI instead
    return abs(first - second) <= tolerance


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()
