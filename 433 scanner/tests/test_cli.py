import json

from ism_scanner.cli import main
from ism_scanner.sources import SourceError, file_lines, rtl_433_lines, simulation_lines


def test_simulate_emits_classified_json(capsys):
    assert main(["simulate", "--cycles", "1"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    events = [json.loads(line) for line in lines]
    categories = {event["category"] for event in events}
    assert "weather" in categories
    assert "tpms" in categories
    assert "unmatched-pulse" in categories


def test_replay_capture(tmp_path, capsys):
    path = tmp_path / "cap.jsonl"
    path.write_text(
        '{"model":"Cotech-367959","id":53,"temperature_F":62.8,"humidity":78}\n',
        encoding="utf-8",
    )
    assert main(["replay", str(path)]) == 0
    event = json.loads(capsys.readouterr().out.splitlines()[0])
    assert event["category"] == "weather"


def test_fake_rtl_433_subprocess(tmp_path):
    fake = tmp_path / "rtl_433"
    fake.write_text(
        '#!/bin/sh\necho \'{"model":"Cotech-367959","id":53,"humidity":78}\'\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    lines = list(
        rtl_433_lines(
            executable=str(fake),
            extra_args=(),
            continuous=False,
        )
    )
    payload = [item for item in lines if isinstance(item, tuple)]
    assert payload[0][0] == "out"
    assert "Cotech-367959" in payload[0][1]


def test_rtl_rejects_unknown_args():
    try:
        list(rtl_433_lines(executable="true", extra_args=("--evil",), continuous=False))
    except SourceError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("expected SourceError")


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "Radio:" in out


def test_capture_round_trips_through_replay(tmp_path):
    from ism_scanner.cli import _ingest, _open_capture
    from ism_scanner.server import Hub

    hub = Hub()
    path = tmp_path / "captures" / "run.jsonl"
    capture = _open_capture(hub, str(path))
    _ingest(hub, simulation_lines(cycles=1, pause=0), hold_seconds=0.0, capture=capture)
    capture.close()
    text = path.read_text(encoding="utf-8")
    assert "stderr:Detected FSK package" in text
    assert '"model":"Cotech-367959"' in text
    replayed = Hub()
    _ingest(replayed, file_lines(path), hold_seconds=0.0)
    assert replayed.snapshot()["decoded"] == hub.snapshot()["decoded"]


def test_live_echo_capture_folds_into_one_weather_identity():
    """Real rtl_433 output (2026-09-04): two Cotech bursts, a repeat decode, two
    companion analyser blocks, and a noise storm."""
    from pathlib import Path

    from ism_scanner.cli import _ingest
    from ism_scanner.server import Hub

    hub = Hub()
    _ingest(hub, file_lines(Path(__file__).parent.parent / "examples" / "live-echoes.jsonl"))
    snap = hub.snapshot()
    weather = [e for e in snap["entities"] if e["category"] == "weather"]
    assert len(weather) == 1
    assert weather[0]["name"] == "Garden weather · Cotech 53"
    assert weather[0]["count"] == 2
    assert weather[0]["repeats"] == 1
    assert weather[0]["companions"] == 2
    assert weather[0]["companion"]["pulse_count"] == 213
    assert snap["decoded"] == 2
    assert snap["repeats"] == 1
    assert snap["companions"] == 2
    assert {e["entity_key"] for e in snap["entities"]} == {
        "cotech-367959:53",
        "pulse:ook:no-clue",
        "noise",
    }
    assert all(
        row["category"] != "unmatched-pulse" or row["kind"] == "pulse" for row in snap["recent"]
    )


def test_simulate_folds_companion_pulses(capsys):
    assert main(["simulate", "--cycles", "1"]) == 0
    events = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    pulses = [event for event in events if event["kind"] == "pulse"]
    assert pulses and pulses[0]["entity_key"] == "pulse:fsk:no-clue"
