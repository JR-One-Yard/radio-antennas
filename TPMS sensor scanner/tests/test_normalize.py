from datetime import UTC, datetime

import pytest

from tpms_scanner.normalize import normalize_event, normalize_line


def accepted(event: dict):
    result = normalize_event(event, received_at=datetime(2026, 9, 2, 6, tzinfo=UTC))
    assert result.rejection is None
    assert result.observation is not None
    return result.observation


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("pressure_kPa", 220, 220.0),
        ("pressure_kpa", "220.5", 220.5),
        ("pressure_PSI", 32, 220.632),
        ("pressure_bar", 2.2, 220.0),
    ],
)
def test_normalizes_pressure_units(field: str, value: object, expected: float) -> None:
    observation = accepted({"type": "TPMS", "model": "Toyota", "id": 7, field: value})
    assert observation.pressure_kpa == expected


def test_preserves_zero_measurements_and_parses_timestamp() -> None:
    observation = accepted(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "0000",
            "pressure_kPa": 0,
            "temperature_C": 0,
            "time": "2026-09-02 05:00:00",
        }
    )
    assert observation.pressure_kpa == 0
    assert observation.temperature_c == 0
    assert observation.observed_at == datetime(2026, 9, 2, 5, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"model": "Acurite", "id": 1}, "non_tpms"),
        ({"type": "TPMS", "model": "Toyota"}, "missing_sensor_id"),
    ],
)
def test_rejects_irrelevant_or_incomplete_events(event: dict, expected: str) -> None:
    assert normalize_event(event).rejection == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("", "blank_line"),
        ("{broken", "malformed_json"),
        ("[]", "non_object_json"),
        ('{"id":"\udcff"}', "malformed_encoding"),
    ],
)
def test_rejects_invalid_lines(line: str, expected: str) -> None:
    assert normalize_line(line).rejection == expected


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"battery_ok": True}, True),
        ({"battery": "OK"}, True),
        ({"battery": "LOW"}, False),
        ({"low_battery": 1}, False),
        ({"low_battery": 0}, True),
    ],
)
def test_normalizes_battery_variants(event: dict, expected: bool) -> None:
    observation = accepted({"type": "TPMS", "model": "Generic", "id": "abc", **event})
    assert observation.battery_ok is expected


def test_normalizes_frequency_hz_to_mhz_and_signal_fields() -> None:
    observation = accepted(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "abc",
            "frequency": 433_920_000,
            "rssi": -40.2,
            "snr": "12.5",
            "noise": -52,
        }
    )
    assert observation.frequency_mhz == 433.92
    assert observation.rssi_db == -40.2
    assert observation.snr_db == 12.5
    assert observation.noise_db == -52


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "-Infinity", "1e9999"])
def test_drops_non_finite_measurements(value: object) -> None:
    observation = accepted(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "abc",
            "pressure_kPa": value,
            "temperature_C": value,
            "rssi": value,
        }
    )
    assert observation.pressure_kpa is None
    assert observation.temperature_c is None
    assert observation.rssi_db is None


def test_drops_pressure_that_overflows_during_unit_conversion() -> None:
    observation = accepted(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "abc",
            "pressure_bar": 1e308,
        }
    )
    assert observation.pressure_kpa is None


def test_huge_json_integer_is_rejected_instead_of_crashing() -> None:
    line = f'{{"type":"TPMS","model":"Toyota","id":{("9" * 5000)}}}'
    assert normalize_line(line).rejection == "malformed_json"


def test_timestamp_utc_overflow_falls_back_to_receipt_time() -> None:
    received = datetime(2026, 9, 2, tzinfo=UTC)
    result = normalize_event(
        {
            "type": "TPMS",
            "model": "Toyota",
            "id": "abc",
            "time": "0001-01-01T00:00:00+23:59",
        },
        received_at=received,
    )
    assert result.observation is not None
    assert result.observation.observed_at == received


def test_rejects_unbounded_sensor_identifier() -> None:
    result = normalize_event({"type": "TPMS", "model": "Toyota", "id": "x" * 129})
    assert result.rejection == "missing_sensor_id"
