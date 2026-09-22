import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest

from tpms_scanner import cli
from tpms_scanner.sources import HEARTBEAT_LINE

NOW = datetime(2026, 9, 2, 5, 0, tzinfo=UTC)


def execute(*args: str, stdin: str = "") -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = cli.run(
        list(args),
        stdin=StringIO(stdin),
        stdout=stdout,
        stderr=stderr,
        now_fn=lambda: NOW,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def fake_executable(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "fake_rtl_433.py"
    target = tmp_path / "rtl_433"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    return target


def test_simulate_table_runs_end_to_end() -> None:
    code, stdout, stderr = execute("simulate")
    assert code == 0
    assert "Toyota" in stdout
    assert "A1B2C3D4" in stdout
    assert "Schrader TPMS" in stdout
    assert "00FF11EE" in stdout
    assert "processed=8 accepted=4 rejected=4 sensors=2" in stderr
    assert "malformed_json=2" in stderr
    assert "non_tpms=2" in stderr


def test_simulate_json_keeps_stdout_machine_readable() -> None:
    code, stdout, stderr = execute("simulate", "--cycles", "1", "--format", "json")
    records = [json.loads(line) for line in stdout.splitlines()]
    assert code == 0
    assert len(records) == 2
    assert {record["sensor_id"] for record in records} == {"A1B2C3D4", "00FF11EE"}
    assert all(record["schema_version"] == 1 for record in records)
    assert set(records[0]) == {
        "age_s",
        "battery_ok",
        "frequency_mhz",
        "model",
        "noise_db",
        "observed_at",
        "pressure_kpa",
        "rssi_db",
        "schema_version",
        "sensor_id",
        "snr_db",
        "stale",
        "status",
        "temperature_c",
    }
    assert "processed=4" in stderr


def test_replay_file_and_stdin_use_same_pipeline(tmp_path: Path) -> None:
    capture = '{"type":"TPMS","model":"Toyota","id":"ABC","pressure_kPa":220}\n'
    path = tmp_path / "capture.jsonl"
    path.write_text(capture, encoding="utf-8")
    file_result = execute("replay", str(path), "--format", "json")
    stdin_result = execute("replay", "-", "--format", "json", stdin=capture)
    assert file_result == stdin_result


def test_filters_flow_through_cli() -> None:
    _, stdout, stderr = execute("simulate", "--model", "schrader")
    assert "Schrader TPMS" in stdout
    assert "Toyota" not in stdout
    assert "filtered=2" in stderr


def test_replay_does_not_replace_newer_source_timestamp() -> None:
    capture = "\n".join(
        [
            '{"type":"TPMS","model":"Toyota","id":"ABC","time":"2026-09-02T05:00:10Z","pressure_kPa":221}',
            '{"type":"TPMS","model":"Toyota","id":"ABC","time":"2026-09-02T05:00:00Z","pressure_kPa":199}',
        ]
    )
    _, stdout, stderr = execute("replay", "-", stdin=capture)
    assert "221.0 kPa" in stdout
    assert "199.0 kPa" not in stdout
    assert "out_of_order=1" in stderr


def test_verbose_rejections_go_only_to_stderr() -> None:
    _, stdout, stderr = execute(
        "simulate",
        "--cycles",
        "1",
        "--format",
        "json",
        "--verbose-rejections",
    )
    for line in stdout.splitlines():
        json.loads(line)
    assert "line 2: non_tpms" in stderr
    assert "line 4: malformed_json" in stderr


def test_live_scan_crosses_fake_subprocess_boundary(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    code, stdout, stderr = execute(
        "scan",
        "--rtl-433",
        str(executable),
        "--frequency",
        "315M",
        "--format",
        "json",
        "--limit",
        "1",
    )
    record = json.loads(stdout)
    assert code == 0
    assert record["model"] == "Fake TPMS"
    assert "accepted=1" in stderr


def test_doctor_reports_present_and_missing_executable(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    present = execute("doctor", "--rtl-433", str(executable), "--json")
    missing = execute("doctor", "--rtl-433", str(tmp_path / "missing"), "--json")
    assert present[0] == 0
    assert json.loads(present[1])["rtl_433"]["ok"] is True
    assert missing[0] == 1
    assert json.loads(missing[1])["rtl_433"]["error"] == "not found"


def test_doctor_sanitizes_version_control_characters(tmp_path: Path) -> None:
    executable = tmp_path / "rtl_433"
    executable.write_text(
        "#!/bin/sh\nprintf '\\033]0;owned\\007rtl_433 fake\\n'\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    code, stdout, _ = execute("doctor", "--rtl-433", str(executable))
    assert code == 0
    assert "\x1b" not in stdout
    assert "\x07" not in stdout
    assert "?]0;owned?" in stdout


@pytest.mark.parametrize(
    "args",
    [
        ("scan", "--frequency", "not-a-frequency"),
        ("scan", "--refresh", "0"),
        ("scan", "--refresh", "nan"),
        ("scan", "--refresh", "1e308"),
        ("scan", "--stale-after", "inf"),
        ("simulate", "--cycles", "0"),
        ("replay", "-", "--stale-after", "-1"),
    ],
)
def test_invalid_arguments_fail_during_parsing(args: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.run(args)
    assert error.value.code == 2


def test_keyboard_interrupt_has_clean_exit(monkeypatch, capsys) -> None:
    def interrupted(**_kwargs):
        raise KeyboardInterrupt
        yield  # pragma: no cover

    monkeypatch.setattr(cli, "rtl_433_lines", interrupted)
    assert cli.main(["scan"]) == 130
    captured = capsys.readouterr()
    assert "scan interrupted" in captured.err
    assert "Traceback" not in captured.err


def test_live_tty_refreshes_to_stale_during_radio_silence(monkeypatch) -> None:
    class TtyBuffer(StringIO):
        def isatty(self) -> bool:
            return True

    started = time.monotonic()

    def now() -> datetime:
        return NOW + timedelta(seconds=time.monotonic() - started)

    def quiet_source(**_kwargs):
        yield '{"type":"TPMS","model":"Toyota","id":"ABC","pressure_kPa":220}'
        time.sleep(0.01)
        yield HEARTBEAT_LINE
        time.sleep(0.04)
        yield HEARTBEAT_LINE

    monkeypatch.setattr(cli, "rtl_433_lines", quiet_source)
    stdout = TtyBuffer()
    code = cli.run(
        ["scan", "--refresh", "0.01", "--stale-after", "0.03"],
        stdout=stdout,
        stderr=StringIO(),
        now_fn=now,
    )
    assert code == 0
    assert "CURRENT" in stdout.getvalue()
    assert "STALE" in stdout.getvalue()


@pytest.mark.parametrize("entrypoint", ["module", "script"])
def test_installed_entrypoints_run_simulation(entrypoint: str) -> None:
    if entrypoint == "module":
        command = [sys.executable, "-m", "tpms_scanner", "simulate", "--cycles", "1"]
    else:
        command = [
            str(Path(sys.executable).with_name("tpms-scan")),
            "simulate",
            "--cycles",
            "1",
        ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0
    assert "Toyota" in result.stdout
    assert "processed=4 accepted=2" in result.stderr
