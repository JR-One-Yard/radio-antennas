from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from tpms_scanner import __version__
from tpms_scanner.normalize import normalize_line
from tpms_scanner.render import format_table, json_line
from tpms_scanner.sources import (
    HEARTBEAT_LINE,
    SourceError,
    file_lines,
    rtl_433_lines,
    simulation_lines,
    stream_lines,
)
from tpms_scanner.tracker import SensorFilter, SensorTracker

_FREQUENCY = re.compile(r"^[0-9]+(?:\.[0-9]+)?(?:[kKmMgG])?$")


@dataclass(slots=True)
class IngestStats:
    processed: int = 0
    accepted: int = 0
    snapshots: int = 0
    rejections: Counter[str] = field(default_factory=Counter)

    def summary(self, sensors: int, evictions: int = 0) -> str:
        rejected = sum(self.rejections.values())
        reasons = ",".join(f"{key}={value}" for key, value in sorted(self.rejections.items()))
        suffix = f" ({reasons})" if reasons else ""
        summary = (
            f"processed={self.processed} accepted={self.accepted} "
            f"rejected={rejected} sensors={sensors}{suffix}"
        )
        return f"{summary} evictions={evictions}" if evictions else summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tpms-scan",
        description="Inspect TPMS telemetry decoded by rtl_433.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan with a local rtl_433 receiver")
    _add_ingest_options(scan)
    scan.add_argument("--frequency", type=_frequency, default="433.92M")
    scan.add_argument("--rtl-433", default="rtl_433", metavar="PATH")
    scan.add_argument(
        "--rtl-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="allowlisted receive/decoder argument; use --rtl-arg=-R for a leading '-'",
    )
    scan.add_argument("--refresh", type=_refresh_interval, default=1.0, metavar="SECONDS")
    scan.add_argument("--limit", type=_positive_int, help="stop after this many accepted updates")

    replay = commands.add_parser("replay", help="read an rtl_433 JSONL capture")
    _add_ingest_options(replay)
    replay.add_argument("path", help="capture path, or '-' for standard input")

    simulate = commands.add_parser("simulate", help="run deterministic hardware-free telemetry")
    _add_ingest_options(simulate)
    simulate.add_argument("--cycles", type=_positive_int, default=2)

    doctor = commands.add_parser("doctor", help="check live-scanning prerequisites")
    doctor.add_argument("--rtl-433", default="rtl_433", metavar="PATH")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable results")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except SourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("scan interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (AttributeError, OSError):
            pass
        return 0


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    now_fn: Callable[[], datetime] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    now = now_fn or (lambda: datetime.now(UTC))
    if args.command == "doctor":
        return _doctor(args, stdout=stdout)

    if args.command == "scan":
        lines = rtl_433_lines(
            executable=args.rtl_433,
            frequency=args.frequency,
            extra_args=tuple(args.rtl_arg),
            stderr_sink=stderr,
            poll_interval=args.refresh,
        )
        live = True
    elif args.command == "replay":
        lines = _stdin_lines(stdin) if args.path == "-" else file_lines(args.path)
        live = False
    else:
        lines = simulation_lines(cycles=args.cycles, start=now())
        live = False

    with closing(lines):
        tracker, stats = _ingest(
            lines,
            args=args,
            live=live,
            stdout=stdout,
            stderr=stderr,
            now_fn=now,
        )
    if args.format == "table":
        if stats.snapshots:
            print("\n---", file=stdout)
        print(
            format_table(tracker.observations(), now=now(), stale_after_s=args.stale_after),
            file=stdout,
        )
    if not args.quiet_summary:
        print(stats.summary(len(tracker), tracker.evictions), file=stderr)
    return 0


def _add_ingest_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="TEXT",
        help="include models containing TEXT; repeat to match any",
    )
    parser.add_argument(
        "--sensor-id",
        action="append",
        default=[],
        metavar="ID",
        help="include an exact sensor ID; repeat to match any",
    )
    parser.add_argument("--stale-after", type=_stale_interval, default=300.0, metavar="SECONDS")
    parser.add_argument("--quiet-summary", action="store_true")
    parser.add_argument("--verbose-rejections", action="store_true")


def _ingest(
    lines: Iterable[str],
    *,
    args: argparse.Namespace,
    live: bool,
    stdout: TextIO,
    stderr: TextIO,
    now_fn: Callable[[], datetime],
) -> tuple[SensorTracker, IngestStats]:
    tracker = SensorTracker()
    filters = SensorFilter(tuple(args.model), tuple(args.sensor_id))
    stats = IngestStats()

    def render_snapshot() -> None:
        observations = tracker.observations()
        if not observations:
            return
        if stats.snapshots:
            print("\n---", file=stdout)
        print(
            format_table(observations, now=now_fn(), stale_after_s=args.stale_after),
            file=stdout,
            flush=True,
        )
        stats.snapshots += 1

    line_number = 0
    for line in lines:
        if line == HEARTBEAT_LINE:
            if live and args.format == "table":
                render_snapshot()
            continue

        line_number += 1
        stats.processed += 1
        result = normalize_line(line, received_at=now_fn())
        if result.rejection is not None:
            _reject(stats, result.rejection, line_number, args, stderr)
            continue

        observation = result.observation
        assert observation is not None
        if not filters.matches(observation):
            _reject(stats, "filtered", line_number, args, stderr)
            continue
        if not tracker.update(observation):
            _reject(stats, "out_of_order", line_number, args, stderr)
            continue

        stats.accepted += 1
        if args.format == "json":
            print(
                json_line(observation, now=now_fn(), stale_after_s=args.stale_after),
                file=stdout,
                flush=live,
            )

        if getattr(args, "limit", None) is not None and stats.accepted >= args.limit:
            break

    return tracker, stats


def _reject(
    stats: IngestStats,
    reason: str,
    line_number: int,
    args: argparse.Namespace,
    stderr: TextIO,
) -> None:
    stats.rejections[reason] += 1
    if args.verbose_rejections:
        print(f"line {line_number}: {reason}", file=stderr)


def _doctor(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved = shutil.which(args.rtl_433)
    if resolved is None and Path(args.rtl_433).is_file():
        resolved = str(Path(args.rtl_433).resolve())

    report: dict[str, object] = {
        "python": {
            "ok": sys.version_info >= (3, 11),
            "version": sys.version.split()[0],
        },
        "rtl_433": {
            "ok": False,
            "path": resolved,
            "version": None,
            "error": None,
        },
        "hardware": {
            "ok": None,
            "note": "Run a live scan to verify USB receiver access and antenna reception.",
        },
    }
    rtl_report = report["rtl_433"]
    assert isinstance(rtl_report, dict)
    if resolved is None:
        rtl_report["error"] = "not found"
    else:
        try:
            return_code, version = _probe_version(resolved)
            rtl_report["version"] = version or "unknown"
            rtl_report["ok"] = return_code == 0
            if return_code != 0:
                rtl_report["error"] = f"version command exited {return_code}"
        except (OSError, subprocess.TimeoutExpired) as error:
            rtl_report["error"] = str(error)

    ok = bool(report["python"]["ok"]) and bool(rtl_report["ok"])  # type: ignore[index]
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True), file=stdout)
    else:
        python = report["python"]
        assert isinstance(python, dict)
        print(f"Python {python['version']}: {'OK' if python['ok'] else 'UNSUPPORTED'}", file=stdout)
        if rtl_report["ok"]:
            path = _safe_human(str(rtl_report["path"]), max_length=240)
            version = _safe_human(str(rtl_report["version"]), max_length=120)
            print(f"rtl_433: OK ({path}; {version})", file=stdout)
        else:
            error = _safe_human(str(rtl_report["error"]), max_length=240)
            print(f"rtl_433: MISSING/FAILED ({error})", file=stdout)
        print(f"Hardware: NOT PROBED ({report['hardware']['note']})", file=stdout)  # type: ignore[index]
    return 0 if ok else 1


def _stdin_lines(stream: TextIO) -> Iterable[str]:
    yield from stream_lines(stream)


def _bounded_interval(value: str, *, maximum: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise argparse.ArgumentTypeError(f"must be greater than zero and at most {maximum:g}")
    return number


def _refresh_interval(value: str) -> float:
    return _bounded_interval(value, maximum=3600)


def _stale_interval(value: str) -> float:
    return _bounded_interval(value, maximum=31_536_000)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _frequency(value: str) -> str:
    if not _FREQUENCY.fullmatch(value) or float(value.rstrip("kKmMgG")) <= 0:
        raise argparse.ArgumentTypeError("use a positive value such as 433.92M or 315M")
    return value


def _safe_human(value: str, *, max_length: int) -> str:
    safe = "".join("?" if unicodedata.category(char).startswith("C") else char for char in value)
    return safe[:max_length]


def _probe_version(executable: str) -> tuple[int, str]:
    command = [executable, "-V"]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    result: queue.Queue[str] = queue.Queue(maxsize=1)
    reader = threading.Thread(
        target=lambda: result.put(process.stdout.readline(4097)),
        daemon=True,
        name="rtl-433-version",
    )
    reader.start()
    try:
        try:
            line = result.get(timeout=5)
        except queue.Empty as error:
            raise subprocess.TimeoutExpired(command, 5) from error
        try:
            return_code = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return_code = process.returncode
        return return_code, line.strip()
    finally:
        _stop_process(process)
        process.stdout.close()
        reader.join(timeout=1)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)
