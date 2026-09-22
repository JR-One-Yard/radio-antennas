import json
from datetime import UTC, datetime, timedelta

from tpms_scanner.models import Observation
from tpms_scanner.normalize import normalize_event
from tpms_scanner.render import format_table, json_line
from tpms_scanner.tracker import SensorFilter, SensorTracker

NOW = datetime(2026, 9, 2, 5, 0, tzinfo=UTC)


def observation(
    sensor_id: str,
    *,
    model: str = "Toyota",
    observed_at: datetime = NOW,
    received_at: datetime | None = None,
    pressure: float = 220.0,
) -> Observation:
    return Observation(
        sensor_id=sensor_id,
        model=model,
        observed_at=observed_at,
        received_at=received_at,
        pressure_kpa=pressure,
    )


def test_updates_sensor_and_ignores_older_observation() -> None:
    tracker = SensorTracker()
    assert tracker.update(observation("ABC", pressure=220))
    assert tracker.update(observation("ABC", observed_at=NOW + timedelta(seconds=1), pressure=221))
    assert not tracker.update(observation("ABC", observed_at=NOW, pressure=199))
    assert len(tracker) == 1
    assert tracker.observations()[0].pressure_kpa == 221


def test_sorts_by_model_then_sensor_id() -> None:
    tracker = SensorTracker()
    tracker.extend(
        [
            observation("B", model="Toyota"),
            observation("C", model="Schrader TPMS"),
            observation("A", model="Toyota"),
        ]
    )
    assert [(item.model, item.sensor_id) for item in tracker.observations()] == [
        ("Schrader TPMS", "C"),
        ("Toyota", "A"),
        ("Toyota", "B"),
    ]


def test_filter_matches_model_substring_and_exact_case_insensitive_id() -> None:
    item = observation("AbC123", model="Schrader TPMS")
    assert SensorFilter(models=("schrader",), sensor_ids=("abc123",)).matches(item)
    assert not SensorFilter(models=("toyota",)).matches(item)
    assert not SensorFilter(sensor_ids=("ABC",)).matches(item)


def test_stale_boundary_and_json_schema() -> None:
    item = observation("ABC")
    before = json.loads(json_line(item, now=NOW + timedelta(seconds=299.999), stale_after_s=300))
    boundary = json.loads(json_line(item, now=NOW + timedelta(seconds=300), stale_after_s=300))
    assert before["stale"] is False
    assert boundary["stale"] is True
    assert boundary["schema_version"] == 1
    assert boundary["observed_at"] == "2026-09-02T05:00:00Z"


def test_table_contains_measurements_and_stale_state() -> None:
    item = Observation(
        sensor_id="ABC",
        model="Toyota",
        observed_at=NOW,
        pressure_kpa=220.25,
        temperature_c=24.5,
        battery_ok=False,
    )
    table = format_table([item], now=NOW + timedelta(minutes=6), stale_after_s=300)
    assert "220.2 kPa" in table
    assert "24.5 C" in table
    assert "LOW" in table
    assert "STALE" in table


def test_empty_table_is_explicit() -> None:
    assert format_table([], now=NOW) == "No TPMS sensors observed."


def test_receipt_time_prevents_future_source_timestamp_poisoning() -> None:
    tracker = SensorTracker()
    future_result = normalize_event(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "ABC",
            "time": "9999-01-01T00:00:00Z",
            "pressure_kPa": 100,
        },
        received_at=NOW,
    )
    later_result = normalize_event(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "ABC",
            "time": "2026-09-02T05:00:01Z",
            "pressure_kPa": 220,
        },
        received_at=NOW + timedelta(seconds=1),
    )
    assert future_result.observation is not None
    assert later_result.observation is not None
    future = future_result.observation
    later = later_result.observation
    assert tracker.update(future)
    assert tracker.update(later)
    assert tracker.observations()[0].pressure_kpa == 220


def test_tracker_evicts_oldest_sensor_at_capacity() -> None:
    tracker = SensorTracker(max_sensors=2)
    tracker.update(observation("A", observed_at=NOW))
    tracker.update(observation("B", observed_at=NOW + timedelta(seconds=1)))
    tracker.update(observation("C", observed_at=NOW + timedelta(seconds=2)))
    assert [item.sensor_id for item in tracker.observations()] == ["B", "C"]
    assert tracker.evictions == 1


def test_table_neutralizes_terminal_control_characters() -> None:
    table = format_table([observation("ABC\n\x1b]0;owned", model="Bad\x1b[31m")], now=NOW)
    assert "\n" not in table.splitlines()[-1]
    assert "\x1b" not in table
    assert "Bad?" in table
