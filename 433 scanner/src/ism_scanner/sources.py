from __future__ import annotations

import json
import os
import pty
import queue
import subprocess
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

MAX_LINE_CHARS = 65_536
OVERSIZED_LINE = "\x00ism-scanner:oversized-line"
HEARTBEAT_LINE = "\x00ism-scanner:heartbeat"
_RTL_VALUE_OPTIONS = {"-C", "-R", "-X", "-Y", "-d", "-g", "-s", "-M", "-T", "-S", "-H"}
_RTL_FLAG_OPTIONS = {"-G", "-q", "-v", "-vv", "-vvv", "-A"}


class SourceError(RuntimeError):
    """A source could not start or stopped unexpectedly."""


def stream_lines(stream: TextIO, *, max_chars: int = MAX_LINE_CHARS) -> Iterator[str]:
    while chunk := stream.readline(max_chars + 1):
        if chunk.endswith(("\n", "\r")):
            line = chunk.rstrip("\r\n")
            yield line if len(line) <= max_chars else OVERSIZED_LINE
            continue
        if len(chunk) <= max_chars:
            yield chunk
            continue
        while chunk and not chunk.endswith(("\n", "\r")):
            chunk = stream.readline(max_chars + 1)
        yield OVERSIZED_LINE


def file_lines(path: str | Path) -> Iterator[tuple[str, str]]:
    try:
        with Path(path).open(encoding="utf-8", errors="surrogateescape") as stream:
            for line in stream_lines(stream):
                yield (
                    "err" if line.startswith("stderr:") else "out",
                    (line.removeprefix("stderr:") if line.startswith("stderr:") else line),
                )
    except OSError as error:
        raise SourceError(
            f"cannot read capture file {path!s}: {error.strerror or error}"
        ) from error


def simulation_lines(
    *,
    cycles: int = 3,
    start: datetime | None = None,
    pause: float = 0.0,
) -> Iterator[tuple[str, str]]:
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    timestamp = start or datetime(2026, 9, 4, 10, 52, tzinfo=UTC)
    for cycle in range(cycles):
        current = timestamp + timedelta(seconds=cycle * 12)
        yield (
            "out",
            json.dumps(
                {
                    "time": _stamp(current),
                    "protocol": 153,
                    "model": "Cotech-367959",
                    "id": 53,
                    "battery_ok": 1,
                    "temperature_F": 62.8 + cycle,
                    "humidity": 78,
                    "rain_mm": 318.6,
                    "wind_dir_deg": 173,
                    "wind_avg_m_s": 0.0,
                    "wind_max_m_s": 0.4 * cycle,
                    "light_lux": 0,
                    "uvi": 0.0,
                    "mod": "ASK",
                    "freq": 433.93,
                    "rssi": -12.1,
                    "snr": 13.0,
                },
                separators=(",", ":"),
            ),
        )
        yield (
            "out",
            json.dumps(
                {
                    "time": _stamp(current + timedelta(seconds=2)),
                    "model": "Toyota",
                    "type": "TPMS",
                    "id": "A1B2C3D4",
                    "pressure_kPa": 220 + cycle,
                    "temperature_C": 24 + cycle,
                    "rssi": -41.2,
                    "freq": 433.92,
                },
                separators=(",", ":"),
            ),
        )
        yield (
            "out",
            json.dumps(
                {
                    "time": _stamp(current + timedelta(seconds=3)),
                    "model": "Silvercrest-Remote",
                    "id": "0x91",
                    "cmd": "ON",
                    "channel": 1,
                    "rssi": -28.0,
                    "freq": 433.92,
                },
                separators=(",", ":"),
            ),
        )
        yield (
            "err",
            f"Detected FSK package {_stamp(current + timedelta(seconds=4))}",
        )
        yield "err", "Analyzing pulses..."
        yield "err", "Total count:   26,  width: 3.03 ms"
        yield "err", "RSSI: -12.1 dB SNR: 15.7 dB Noise: -27.8 dB"
        yield "err", "Guessing modulation: No clue..."
        yield "err", "view at https://triq.org/pdv/#demo"
        yield "out", "{not-json"
        if pause:
            time.sleep(pause)


def rtl_433_lines(
    *,
    executable: str = "rtl_433",
    frequency: str = "433.92M",
    extra_args: tuple[str, ...] = (),
    stderr_history: int = 40,
    stderr_sink: TextIO | None = None,
    continuous: bool = True,
    poll_interval: float = 1.0,
) -> Iterator[tuple[str, str] | str]:
    _validate_extra_args(extra_args)
    # usec lets the deduper tell two bursts in the same second apart; the analyser's
    # "Detected OOK package <time>" line honours the same format.
    command = [
        executable,
        "-f",
        frequency,
        "-M",
        "time:iso:usec:utc",
        "-F",
        "json",
        *extra_args,
    ]
    try:
        process, stdout, stderr = _start_rtl_433(command)
    except FileNotFoundError as error:
        raise SourceError(
            f"{executable!r} was not found; install rtl_433 or pass --rtl-433 PATH"
        ) from error
    except OSError as error:
        raise SourceError(f"could not start {executable!r}: {error}") from error

    errors: deque[str] = deque(maxlen=max(1, stderr_history))
    output: queue.Queue[object] = queue.Queue(maxsize=128)
    stop_readers = threading.Event()
    end_of_output = object()
    stdout_thread = threading.Thread(
        target=_queue_stream,
        args=(stdout, output, stop_readers, "out", end_of_output),
        daemon=True,
        name="rtl-433-stdout",
    )
    stderr_thread = threading.Thread(
        target=_queue_stderr,
        args=(stderr, output, errors, stderr_sink, stop_readers, end_of_output),
        daemon=True,
        name="rtl-433-stderr",
    )
    completed = False
    cleanup_failure: str | None = None
    ended = 0
    try:
        stdout_thread.start()
        stderr_thread.start()
        heartbeat_deadline = time.monotonic() + poll_interval
        while ended < 2:
            timeout = max(0.0, heartbeat_deadline - time.monotonic())
            try:
                item = output.get(timeout=timeout)
            except queue.Empty:
                yield HEARTBEAT_LINE
                heartbeat_deadline = time.monotonic() + poll_interval
                continue
            if item is end_of_output:
                ended += 1
                continue
            if isinstance(item, BaseException):
                raise SourceError(f"could not read rtl_433 output: {item}") from item
            if item is HEARTBEAT_LINE:
                continue
            assert isinstance(item, tuple)
            yield item
            if time.monotonic() >= heartbeat_deadline:
                yield HEARTBEAT_LINE
                heartbeat_deadline = time.monotonic() + poll_interval
        try:
            return_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired as error:
            raise SourceError("rtl_433 closed its output but did not exit") from error
        completed = True
        if return_code != 0:
            detail = "\n".join(errors) or "no diagnostic output"
            raise SourceError(f"rtl_433 exited with status {return_code}: {detail}")
        if continuous:
            raise SourceError("rtl_433 ended unexpectedly with status 0")
    finally:
        stop_readers.set()
        if not completed and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    cleanup_failure = f"could not reap rtl_433 process {process.pid} after SIGKILL"
        stdout.close()
        stderr.close()
        if stdout_thread.ident is not None:
            stdout_thread.join(timeout=1)
        if stderr_thread.ident is not None:
            stderr_thread.join(timeout=1)
        if cleanup_failure is not None and stderr_sink is not None:
            with suppress(BrokenPipeError, OSError, ValueError):
                print(f"[rtl_433] {cleanup_failure}", file=stderr_sink, flush=True)
        if cleanup_failure is not None:
            raise SourceError(cleanup_failure)


def _start_rtl_433(command: list[str]) -> tuple[subprocess.Popen, TextIO, TextIO]:
    """JSON on a PTY so it flushes; analyser text on a pipe because stderr is unbuffered."""
    try:
        master_out, slave_out = pty.openpty()
    except OSError:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            bufsize=1,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        return process, process.stdout, process.stderr
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=slave_out,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            bufsize=1,
            close_fds=True,
        )
    except (FileNotFoundError, OSError):
        os.close(master_out)
        os.close(slave_out)
        raise
    os.close(slave_out)
    stdout = os.fdopen(master_out, "r", encoding="utf-8", errors="surrogateescape")
    assert process.stderr is not None
    return process, stdout, process.stderr


def _queue_stream(
    stream: TextIO,
    destination: queue.Queue[object],
    stop: threading.Event,
    channel: str,
    sentinel: object,
) -> None:
    try:
        for line in stream_lines(stream):
            if not _put_if_running(destination, (channel, line), stop):
                return
    except (OSError, UnicodeError, ValueError) as error:
        _put_if_running(destination, error, stop)
    finally:
        _put_if_running(destination, sentinel, stop)


def _queue_stderr(
    stream: TextIO,
    destination: queue.Queue[object],
    errors: deque[str],
    sink: TextIO | None,
    stop: threading.Event,
    sentinel: object,
) -> None:
    try:
        # Analyser "view at https://triq.org/pdv/#..." lines carry the whole pulse
        # train and routinely exceed 4 KiB; truncating them would drop the block's
        # terminator and its pulse-view link, so allow the same size as stdout.
        for line in stream_lines(stream):
            text = (
                "oversized diagnostic omitted"
                if line == OVERSIZED_LINE
                else _safe_text(line.strip()[:512])
            )
            if text:
                errors.append(text)
                if sink is not None:
                    try:
                        print(f"[rtl_433] {text}", file=sink, flush=True)
                    except (BrokenPipeError, OSError, ValueError):
                        sink = None
            if not _put_if_running(destination, ("err", line), stop):
                return
    except (OSError, UnicodeError, ValueError) as error:
        _put_if_running(destination, error, stop)
    finally:
        _put_if_running(destination, sentinel, stop)


def _put_if_running(
    destination: queue.Queue[object],
    item: object,
    stop: threading.Event,
) -> bool:
    while not stop.is_set():
        try:
            destination.put(item, timeout=0.1)
            return True
        except queue.Full:
            continue
    return False


def _validate_extra_args(arguments: tuple[str, ...]) -> None:
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option in _RTL_FLAG_OPTIONS:
            index += 1
            continue
        if option in _RTL_VALUE_OPTIONS and index + 1 < len(arguments):
            index += 2
            continue
        allowed = ", ".join(sorted(_RTL_FLAG_OPTIONS | _RTL_VALUE_OPTIONS))
        raise SourceError(f"unsupported --rtl-arg {option!r}; allowed receive options: {allowed}")


def _safe_text(value: str) -> str:
    return "".join("?" if unicodedata.category(char).startswith("C") else char for char in value)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
