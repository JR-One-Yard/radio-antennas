from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Iterable, Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

MAX_LINE_CHARS = 65_536
OVERSIZED_LINE = "\x00tpms-scanner:oversized-line"
HEARTBEAT_LINE = "\x00tpms-scanner:heartbeat"
_RTL_VALUE_OPTIONS = {"-C", "-R", "-X", "-Y", "-d", "-g", "-s"}
_RTL_FLAG_OPTIONS = {"-G", "-q", "-v", "-vv", "-vvv"}


class SourceError(RuntimeError):
    """A source could not start or stopped unexpectedly."""


def stream_lines(stream: TextIO, *, max_chars: int = MAX_LINE_CHARS) -> Iterator[str]:
    """Read bounded records and drain oversized lines without retaining them."""
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


def file_lines(path: str | Path) -> Iterator[str]:
    try:
        with Path(path).open(encoding="utf-8", errors="surrogateescape") as stream:
            yield from stream_lines(stream)
    except OSError as error:
        raise SourceError(
            f"cannot read capture file {path!s}: {error.strerror or error}"
        ) from error


def simulation_lines(
    *,
    cycles: int = 2,
    start: datetime | None = None,
) -> Iterator[str]:
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    timestamp = start or datetime(2026, 9, 2, 5, 0, tzinfo=UTC)
    for cycle in range(cycles):
        current = timestamp + timedelta(seconds=cycle * 30)
        events: Iterable[object] = (
            {
                "time": _timestamp(current),
                "model": "Toyota",
                "type": "TPMS",
                "id": "A1B2C3D4",
                "pressure_kPa": 220.0 + cycle,
                "temperature_C": 24.0 + cycle,
                "battery_ok": 1,
                "status": "OK",
                "rssi": -41.2,
                "frequency": 433_920_000,
            },
            {
                "time": _timestamp(current + timedelta(seconds=1)),
                "model": "Acurite-Tower",
                "id": 1234,
                "temperature_C": 19.5,
            },
            {
                "time": _timestamp(current + timedelta(seconds=2)),
                "model": "Schrader TPMS",
                "id": "00FF11EE",
                "pressure_PSI": 32.0 + cycle,
                "temperature_C": 27.0,
                "battery": "LOW" if cycle else "OK",
                "snr": 14.1,
            },
        )
        for event in events:
            yield json.dumps(event, separators=(",", ":"))
        yield "{not-json"


def rtl_433_lines(
    *,
    executable: str = "rtl_433",
    frequency: str = "433.92M",
    extra_args: tuple[str, ...] = (),
    stderr_history: int = 20,
    stderr_sink: TextIO | None = None,
    continuous: bool = True,
    poll_interval: float = 1.0,
) -> Iterator[str]:
    _validate_extra_args(extra_args)
    command = [
        executable,
        "-f",
        frequency,
        "-M",
        "time:iso:utc",
        "-F",
        "json",
        *extra_args,
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            bufsize=1,
        )
    except FileNotFoundError as error:
        raise SourceError(
            f"{executable!r} was not found; install rtl_433 or pass --rtl-433 PATH"
        ) from error
    except OSError as error:
        raise SourceError(f"could not start {executable!r}: {error}") from error

    assert process.stdout is not None
    assert process.stderr is not None
    errors: deque[str] = deque(maxlen=max(1, stderr_history))
    output: queue.Queue[object] = queue.Queue(maxsize=64)
    stop_readers = threading.Event()
    end_of_output = object()
    stdout_thread = threading.Thread(
        target=_queue_stdout,
        args=(process.stdout, output, stop_readers, end_of_output),
        daemon=True,
        name="rtl-433-stdout",
    )
    stderr_thread = threading.Thread(
        target=_drain_stderr,
        args=(process.stderr, errors, stderr_sink, stop_readers),
        daemon=True,
        name="rtl-433-stderr",
    )
    completed = False
    cleanup_failure: str | None = None
    try:
        stdout_thread.start()
        stderr_thread.start()
        heartbeat_deadline = time.monotonic() + poll_interval
        while True:
            timeout = max(0.0, heartbeat_deadline - time.monotonic())
            try:
                item = output.get(timeout=timeout)
            except queue.Empty:
                yield HEARTBEAT_LINE
                heartbeat_deadline = time.monotonic() + poll_interval
                continue
            if item is end_of_output:
                break
            if isinstance(item, BaseException):
                raise SourceError(f"could not read rtl_433 output: {item}") from item
            assert isinstance(item, str)
            yield item
            if time.monotonic() >= heartbeat_deadline:
                yield HEARTBEAT_LINE
                heartbeat_deadline = time.monotonic() + poll_interval
        try:
            return_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired as error:
            raise SourceError("rtl_433 closed its output but did not exit") from error
        completed = True
        stderr_thread.join(timeout=1)
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
        process.stdout.close()
        process.stderr.close()
        if stdout_thread.ident is not None:
            stdout_thread.join(timeout=1)
        if stderr_thread.ident is not None:
            stderr_thread.join(timeout=1)
        if cleanup_failure is not None and stderr_sink is not None:
            with suppress(BrokenPipeError, OSError, ValueError):
                print(f"[rtl_433] {cleanup_failure}", file=stderr_sink, flush=True)
        if cleanup_failure is not None:
            raise SourceError(cleanup_failure)


def _drain_stderr(
    stream: TextIO,
    destination: deque[str],
    sink: TextIO | None,
    stop: threading.Event,
) -> None:
    for line in stream_lines(stream, max_chars=4096):
        if stop.is_set():
            break
        text = (
            "oversized diagnostic omitted" if line == OVERSIZED_LINE else _safe_text(line.strip())
        )
        if text:
            destination.append(text)
            if sink is not None:
                try:
                    print(f"[rtl_433] {text}", file=sink, flush=True)
                except (BrokenPipeError, OSError, ValueError):
                    sink = None


def _queue_stdout(
    stream: TextIO,
    destination: queue.Queue[object],
    stop: threading.Event,
    sentinel: object,
) -> None:
    try:
        for line in stream_lines(stream):
            if not _put_if_running(destination, line, stop):
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


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
