import json
import time
from io import StringIO
from pathlib import Path

import pytest

from tpms_scanner.sources import (
    HEARTBEAT_LINE,
    MAX_LINE_CHARS,
    OVERSIZED_LINE,
    SourceError,
    file_lines,
    rtl_433_lines,
    simulation_lines,
    stream_lines,
)


def fake_executable(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "fake_rtl_433.py"
    target = tmp_path / "rtl_433"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    return target


def test_stream_handles_blank_and_final_unterminated_lines() -> None:
    assert list(stream_lines(StringIO("first\n\nlast"))) == ["first", "", "last"]


def test_stream_drains_oversized_line_and_continues() -> None:
    stream = StringIO(f"{'x' * (MAX_LINE_CHARS + 1)}\nnext\n")
    assert list(stream_lines(stream)) == [OVERSIZED_LINE, "next"]


def test_file_source_reads_jsonl(tmp_path: Path) -> None:
    capture = tmp_path / "capture.jsonl"
    capture.write_text('{"id":1}\n{"id":2}', encoding="utf-8")
    assert list(file_lines(capture)) == ['{"id":1}', '{"id":2}']


def test_file_source_replaces_invalid_utf8_without_crashing(tmp_path: Path) -> None:
    capture = tmp_path / "capture.jsonl"
    capture.write_bytes(b'{"id":"\xff"}\n{"id":2}\n')
    lines = list(file_lines(capture))
    assert "\udcff" in lines[0]
    assert lines[1] == '{"id":2}'


def test_missing_capture_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="cannot read capture file"):
        list(file_lines(tmp_path / "missing.jsonl"))


def test_simulator_is_deterministic_and_includes_failure_cases() -> None:
    first = list(simulation_lines(cycles=1))
    second = list(simulation_lines(cycles=1))
    assert first == second
    assert len(first) == 4
    assert first[-1] == "{not-json"


def test_fake_rtl_process_receives_frequency_and_json_format(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    lines = list(rtl_433_lines(executable=str(executable), frequency="315M", continuous=False))
    event = json.loads(lines[0])
    assert event["_received_frequency"] == "315M"
    assert event["_received_format"] == "json"
    assert event["_received_meta"] == "time:iso:utc"


def test_clean_rtl_exit_is_unexpected_for_live_scan(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    with pytest.raises(SourceError, match="ended unexpectedly"):
        list(rtl_433_lines(executable=str(executable)))


def test_rejects_output_or_unknown_passthrough_options(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    with pytest.raises(SourceError, match="unsupported --rtl-arg"):
        list(rtl_433_lines(executable=str(executable), extra_args=("-F", "mqtt://host")))


def test_missing_rtl_executable_has_install_guidance() -> None:
    with pytest.raises(SourceError, match="install rtl_433"):
        list(rtl_433_lines(executable="/definitely/missing/rtl_433"))


def test_rtl_failure_includes_status_and_stderr(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    with pytest.raises(SourceError, match=r"status 7.*fake receiver failure"):
        list(rtl_433_lines(executable=str(executable), extra_args=("-q",)))


def test_closing_source_terminates_sleeping_child(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    source = rtl_433_lines(executable=str(executable), extra_args=("-G",))
    assert "FAKE0001" in next(source)
    started = time.monotonic()
    source.close()
    assert time.monotonic() - started < 3


def test_live_source_emits_heartbeat_while_receiver_is_quiet(tmp_path: Path) -> None:
    executable = fake_executable(tmp_path)
    source = rtl_433_lines(
        executable=str(executable),
        extra_args=("-G",),
        poll_interval=0.01,
    )
    line = next(source)
    while line == HEARTBEAT_LINE:
        line = next(source)
    assert "FAKE0001" in line
    assert next(source) == HEARTBEAT_LINE
    source.close()


def test_stderr_sink_failure_does_not_block_drain(tmp_path: Path) -> None:
    class BrokenSink(StringIO):
        def write(self, _value: str) -> int:
            raise BrokenPipeError

    executable = fake_executable(tmp_path)
    with pytest.raises(SourceError, match="fake receiver failure"):
        list(
            rtl_433_lines(
                executable=str(executable),
                extra_args=("-q",),
                stderr_sink=BrokenSink(),
            )
        )
