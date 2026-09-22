from datetime import UTC, datetime, timedelta

from ism_scanner.census import Census
from ism_scanner.normalize import sighting_from_decoded, sighting_from_pulse


def _cotech(seconds: int, **fields):
    stamp = (datetime(2026, 9, 4, 10, 52, 35, tzinfo=UTC) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    return sighting_from_decoded(
        {
            "model": "Cotech-367959",
            "id": 53,
            "humidity": 78,
            "temperature_F": 62.8,
            "time": stamp,
            **fields,
        }
    )


def test_same_sensor_collapses():
    census = Census()
    census.ingest(_cotech(0))
    census.ingest(_cotech(60, humidity=79))
    snap = census.snapshot()
    assert snap["entity_count"] == 1
    assert snap["decoded"] == 2
    assert snap["entities"][0]["count"] == 2
    assert snap["entities"][0]["fields"]["humidity"] == 79
    assert snap["entities"][0]["name"] == "Garden weather · Cotech 53"
    assert "17.1 °C" in snap["entities"][0]["summary"]


def test_repeats_and_companions_do_not_mint_rows():
    census = Census()
    original = _cotech(0)
    census.ingest(original)
    repeat = _cotech(0)
    repeat["duplicate_of"] = original["entity_key"]
    census.ingest(repeat)
    pulse = sighting_from_pulse(
        {
            "kind": "pulse",
            "rf_kind": "OOK",
            "time": "2026-09-04T10:52:35",
            "pulse_count": 219,
            "width_ms": 253.9,
            "rssi": -11.1,
            "modulation": "Pulse Width Modulation with multiple packets",
            "flex": "n=name,m=OOK_PWM,s=493,l=975,r=5883",
        }
    )
    pulse["companion_of"] = original["entity_key"]
    census.ingest(pulse)
    snap = census.snapshot()
    assert snap["entity_count"] == 1
    assert snap["decoded"] == 1
    assert snap["repeats"] == 1
    assert snap["companions"] == 1
    assert len(snap["recent"]) == 1
    entity = snap["entities"][0]
    assert entity["repeats"] == 1
    assert entity["companions"] == 1
    assert entity["companion"]["pulse_count"] == 219


def test_cadence_and_trend():
    census = Census()
    for step in range(6):
        census.ingest(_cotech(step * 16, temperature_F=60 + step))
    entity = census.snapshot()["entities"][0]
    assert entity["cadence_s"] == 16.0
    assert len(entity["trend"]) == 6
    assert entity["trend"][-1]["temperature_C"] == round((65 - 32) * 5 / 9, 1)


def test_noise_counts_separately_and_is_quiet():
    census = Census()
    for _ in range(5):
        census.ingest(
            sighting_from_pulse(
                {
                    "kind": "pulse",
                    "rf_kind": "OOK",
                    "pulse_count": 1,
                    "modulation": "Single pulse detected. Probably Frequency Shift Keying "
                    "or just noise...",
                    "time": "2026-09-04T10:52:36",
                }
            )
        )
    snap = census.snapshot()
    assert snap["noise"] == 5
    assert snap["pulses"] == 0
    assert snap["entity_count"] == 1
    assert snap["quiet_count"] == 1
    assert snap["entities"][0]["entity_key"] == "noise"


def test_digest_counts_last_hour_only():
    census = Census()
    now = datetime.now(UTC)
    old = sighting_from_decoded(
        {
            "model": "Cotech-367959",
            "id": 53,
            "humidity": 70,
            "time": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    census.ingest(old)
    for minutes in (30, 20, 10):
        census.ingest(
            sighting_from_decoded(
                {
                    "model": "Cotech-367959",
                    "id": 53,
                    "humidity": 70 + minutes,
                    "temperature_F": 50 + minutes,
                    "time": (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        )
    digest = census.digest(now=now)
    assert digest["total"] == 3
    item = digest["entities"][0]
    assert item["count"] == 3
    assert item["name"] == "Garden weather · Cotech 53"
    assert item["ranges"]["humidity"] == {"min": 80, "max": 100, "last": 80}


def test_stale_scales_with_cadence():
    census = Census()
    now = datetime.now(UTC)
    for minutes in (40, 30, 20, 10):
        census.ingest(
            sighting_from_decoded(
                {
                    "model": "Slow-Sensor",
                    "id": 1,
                    "humidity": 1,
                    "time": (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        )
    entity = census.snapshot()["entities"][0]
    assert entity["cadence_s"] == 600.0
    assert entity["stale"] is False  # 10 min old, allowed 30 min
