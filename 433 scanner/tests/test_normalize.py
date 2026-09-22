from pathlib import Path

from ism_scanner.describe import brand_of, parse_flex
from ism_scanner.normalize import (
    PulseAssembler,
    interpret_line,
    sighting_from_decoded,
    sighting_from_pulse,
)

FIXTURE = Path(__file__).parent / "fixtures" / "analyser-stderr.txt"


def test_decoded_json():
    events = interpret_line(
        '{"time":"2026-09-04T10:52:35","model":"Cotech-367959","id":53,"humidity":78}',
        PulseAssembler(),
        from_stderr=False,
    )
    assert len(events) == 1
    assert events[0]["kind"] == "decoded"
    assert events[0]["device_id"] == "53"
    assert events[0]["time"] == "2026-09-04T10:52:35Z"


def test_malformed_json_is_ignored():
    assert interpret_line("{not-json", PulseAssembler(), from_stderr=False) == []


def test_analyser_no_clue_block():
    assembler = PulseAssembler()
    seen = []
    for line in FIXTURE.read_text().splitlines():
        seen.extend(interpret_line(line, assembler, from_stderr=True))
    leftover = assembler.flush()
    if leftover:
        seen.append(leftover)
    pulses = [event for event in seen if event["kind"] == "pulse"]
    assert pulses
    assert pulses[0]["rf_kind"] == "FSK"
    assert pulses[0]["category"] == "unmatched-pulse"
    assert pulses[0]["rssi"] == -12.1
    assert pulses[0]["time"].endswith("Z")
    assert pulses[0]["entity_key"] == "pulse:fsk:no-clue"


def test_blank_stderr_line_terminates_a_no_clue_block():
    """rtl_433 25.12 prints no 'view at' line for OOK 'No clue' blocks; the blank
    line that follows is the only terminator."""
    assembler = PulseAssembler()
    lines = [
        "Detected OOK package\t2026-09-04T12:04:19.168307",
        "Analyzing pulses...",
        "Total count:    6,  width: 1.30 ms\t\t( 1331 S)",
        "RSSI: -12.1 dB SNR: 11.3 dB Noise: -23.5 dB",
        "Guessing modulation: No clue...",
    ]
    for line in lines:
        assert interpret_line(line, assembler, from_stderr=True) == []
    flushed = interpret_line("", assembler, from_stderr=True)
    assert len(flushed) == 1
    assert flushed[0]["entity_key"] == "pulse:ook:no-clue"
    assert flushed[0]["time"] == "2026-09-04T12:04:19.168307Z"
    # A blank line with nothing open (or only a header) is inert.
    assert interpret_line("", assembler, from_stderr=True) == []
    interpret_line("Detected OOK package 2026-09-04T12:04:20", assembler, from_stderr=True)
    assert interpret_line("", assembler, from_stderr=True) == []


def test_usec_timestamps_survive():
    assembler = PulseAssembler()
    interpret_line("Detected OOK package 2026-09-04T11:36:19.104211", assembler, from_stderr=True)
    interpret_line("Total count:   26,  width: 3.03 ms", assembler, from_stderr=True)
    pulse = assembler.flush()
    assert pulse["time"] == "2026-09-04T11:36:19.104211Z"


def test_frequency_mhz_to_hz():
    sighting = sighting_from_decoded({"freq": 433.93, "model": "x"})
    assert abs(sighting["frequency_hz"] - 433_930_000) < 1


def test_pulse_identity_groups_by_timing_not_count():
    def pulse(count, short):
        return sighting_from_pulse(
            {
                "kind": "pulse",
                "rf_kind": "OOK",
                "pulse_count": count,
                "modulation": "Pulse Width Modulation with multiple packets",
                "flex": f"n=name,m=OOK_PWM,s={short},l=975,r=5883",
            }
        )

    assert pulse(215, 493)["entity_key"] == pulse(219, 495)["entity_key"]
    assert pulse(215, 493)["entity_key"] != pulse(215, 113)["entity_key"]


def test_no_clue_bursts_share_one_identity():
    def pulse(count):
        return sighting_from_pulse(
            {"kind": "pulse", "rf_kind": "OOK", "pulse_count": count, "modulation": "No clue..."}
        )

    assert pulse(9)["entity_key"] == pulse(70)["entity_key"] == "pulse:ook:no-clue"
    assert pulse(9)["name"] == "Unrecognised OOK chatter"


def test_tpms_units_are_derived_like_the_tpms_scanner():
    sighting = sighting_from_decoded(
        {
            "model": "Schrader",
            "type": "TPMS",
            "id": "1",
            "pressure_PSI": 32.0,
            "temperature_F": 68.0,
        }
    )
    assert sighting["fields"]["pressure_kPa"] == round(32.0 * 6.894757, 1)
    assert sighting["fields"]["temperature_C"] == 20.0
    assert sighting["fields"]["pressure_PSI"] == 32.0  # original kept


def test_weather_summary_reads_like_a_person():
    sighting = sighting_from_decoded(
        {
            "model": "Cotech-367959",
            "id": 53,
            "temperature_F": 61.7,
            "humidity": 81,
            "rain_mm": 318.6,
            "wind_avg_m_s": 1.0,
            "wind_max_m_s": 2.0,
            "wind_dir_deg": 42,
            "battery_ok": 0,
        }
    )
    assert sighting["name"] == "Garden weather · Cotech 53"
    assert sighting["summary"] == (
        "16.5 °C · 81 % RH · rain 318.6 mm · wind 4 km/h (gusts 7) from NE · battery low"
    )


def test_brand_and_flex_helpers():
    assert brand_of("Cotech-367959") == "Cotech"
    assert brand_of("Hyundai-VDO") == "Hyundai VDO"
    assert brand_of("Fineoffset-WH51") == "Fineoffset WH51"
    assert parse_flex("n=name,m=OOK_PWM,s=493,l=975") == {
        "n": "name",
        "m": "OOK_PWM",
        "s": 493,
        "l": 975,
    }
