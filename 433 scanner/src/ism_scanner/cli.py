from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterable, Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from ism_scanner import __version__, procs
from ism_scanner.dedup import Deduper
from ism_scanner.normalize import PulseAssembler, interpret_line
from ism_scanner.server import Hub, serve_http
from ism_scanner.sources import (
    HEARTBEAT_LINE,
    OVERSIZED_LINE,
    SourceError,
    file_lines,
    rtl_433_lines,
    simulation_lines,
)

_FREQUENCY = re.compile(r"^[0-9]+(?:\.[0-9]+)?(?:[kKmMgG])?$")
DEFAULT_RTL_ARGS = ("-d", "0", "-g", "0", "-A", "-s", "1024k", "-M", "level", "-M", "protocol")
LIVE_POLL_S = 0.25  # heartbeat cadence; also bounds how long a companion pulse is held


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ism-scan",
        description="Hear everything on 433 MHz and guess what it is.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="open the live census UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=4330)
    serve.add_argument("--frequency", type=_frequency, default="433.92M")
    serve.add_argument("--rtl-433", default="rtl_433", metavar="PATH")
    serve.add_argument("--rtl-arg", action="append", default=[], metavar="ARG")
    serve.add_argument("--live-only", action="store_true", help="do not fall back to simulation")
    serve.add_argument("--simulate", action="store_true", help="do not open the radio")
    serve.add_argument("--replay", metavar="PATH", help="replay a JSONL/analyser capture")
    serve.add_argument(
        "--capture",
        metavar="PATH",
        help="also append raw rtl_433 lines to this JSONL file (replayable; off by default)",
    )

    replay = commands.add_parser("replay", help="print classified JSONL from a capture")
    replay.add_argument("path")

    simulate = commands.add_parser("simulate", help="print classified demo events")
    simulate.add_argument("--cycles", type=int, default=2)

    commands.add_parser("doctor", help="check rtl_433, the USB receiver, and who holds it")
    commands.add_parser("stop", help="stop any other `ism-scan serve` (safely, by pid)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "stop":
        return _stop()
    if args.command == "simulate":
        return _print_source(simulation_lines(cycles=args.cycles))
    if args.command == "replay":
        return _print_source(file_lines(args.path))
    return _serve(args)


def _serve(args: argparse.Namespace) -> int:
    hub = Hub()
    extra = tuple(args.rtl_arg) if args.rtl_arg else DEFAULT_RTL_ARGS
    hub.set_status(frequency=args.frequency, capture=args.capture)
    server = serve_http(hub, host=args.host, port=args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"Over the Fence listening at {url}", file=sys.stderr)
    worker = threading.Thread(
        target=_ingest_forever,
        args=(hub, args, extra),
        daemon=True,
        name="ism-ingest",
    )
    hub.attach_ingest(worker)
    worker.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopping.", file=sys.stderr)
        return 0
    finally:
        server.shutdown()
    return 0


def _ingest_forever(hub: Hub, args: argparse.Namespace, extra: tuple[str, ...]) -> None:
    try:
        _ingest_forever_inner(hub, args, extra)
    except Exception as error:  # noqa: BLE001
        hub.set_status(
            state="error",
            message=f"Ingest thread died: {error}",
            workaround="ingest-thread",
        )
        print(f"ingest thread died: {error}", file=sys.stderr)
    else:
        hub.log("Ingest thread finished", level="info")


def _ingest_forever_inner(hub: Hub, args: argparse.Namespace, extra: tuple[str, ...]) -> None:
    capture = _open_capture(hub, args.capture)
    try:
        if args.simulate:
            hub.set_status(state="simulating", source="simulate", message="Demo neighbourhood")
            _ingest(hub, simulation_lines(cycles=10_000, pause=0.8), capture=capture)
            return
        if args.replay:
            hub.set_status(state="replaying", source=str(args.replay), message="Replay capture")
            _ingest(hub, file_lines(args.replay), hold_seconds=0.0, capture=capture)
            hub.set_status(state="idle", message="Replay finished")
            return
        owners = procs.rtl_433_owners()
        if owners:
            hub.set_status(
                radio_owner=[{"pid": p.pid, "command": p.short} for p in owners],
                message=f"Another rtl_433 (pid {owners[0].pid}) already holds the radio; "
                "starting ours will fail unless it stops. Try `ism-scan stop`.",
            )
        try:
            hub.set_status(
                state="listening",
                source="rtl_433",
                message=f"Live at {args.frequency}",
                workaround=None,
            )
            _ingest(
                hub,
                rtl_433_lines(
                    executable=args.rtl_433,
                    frequency=args.frequency,
                    extra_args=extra,
                    continuous=True,
                    poll_interval=LIVE_POLL_S,
                ),
                capture=capture,
            )
        except SourceError as error:
            detail = str(error)
            if owners:
                detail += f" (rtl_433 pid {owners[0].pid} was already running)"
            if args.live_only:
                hub.set_status(state="error", message=detail)
                print(error, file=sys.stderr)
                return
            hub.set_status(
                state="simulating",
                source="simulate",
                message=f"Radio unavailable ({detail}). Showing a demo neighbourhood instead.",
                workaround="live-to-simulate-fallback",
            )
            _ingest(hub, simulation_lines(cycles=10_000, pause=0.8), capture=capture)
    finally:
        if capture is not None:
            with suppress(OSError):
                capture.close()


def _open_capture(hub: Hub, path: str | None) -> IO[str] | None:
    if not path:
        return None
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("a", encoding="utf-8")
    except OSError as error:
        hub.log(f"Capture disabled: cannot open {path}: {error}", level="warn")
        return None
    hub.log(f"Capturing raw rtl_433 lines to {path}")
    return handle


def _ingest(
    hub: Hub,
    source: Iterable[object],
    *,
    hold_seconds: float = LIVE_POLL_S,
    capture: IO[str] | None = None,
) -> None:
    assembler = PulseAssembler()
    deduper = Deduper(hold_seconds=hold_seconds)
    raw_lines = 0
    try:
        for item in source:
            if item == HEARTBEAT_LINE:
                for ready in deduper.tick():
                    hub.publish(ready)
                continue
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            channel, line = item
            raw_lines += 1
            hub.saw_line(raw_lines)
            if line == OVERSIZED_LINE:
                continue
            if capture is not None:
                _write_capture(capture, channel, str(line))
            try:
                heard = interpret_line(str(line), assembler, from_stderr=channel == "err")
            except Exception as error:  # noqa: BLE001
                hub.set_status(message=f"Skipped a malformed line: {error}")
                continue
            for sighting in heard:
                for ready in deduper.push(sighting):
                    hub.publish(ready)
    except Exception as error:  # noqa: BLE001
        hub.set_status(state="error", message=f"Ingest failed: {error}")
        raise
    finally:
        hub.saw_line(raw_lines)
        leftover = assembler.flush()
        if leftover:
            for ready in deduper.push(leftover):
                hub.publish(ready)
        for ready in deduper.flush():
            hub.publish(ready)


def _write_capture(capture: IO[str], channel: str, line: str) -> None:
    try:
        capture.write(("stderr:" if channel == "err" else "") + line + "\n")
        capture.flush()
    except OSError:
        pass


def _print_source(source: Iterator[tuple[str, str]]) -> int:
    assembler = PulseAssembler()
    deduper = Deduper(hold_seconds=0.0)
    for channel, line in source:
        if line == OVERSIZED_LINE:
            continue
        for sighting in interpret_line(line, assembler, from_stderr=channel == "err"):
            for ready in deduper.push(sighting):
                print(json.dumps(ready, separators=(",", ":")))
    leftover = assembler.flush()
    if leftover:
        for ready in deduper.push(leftover):
            print(json.dumps(ready, separators=(",", ":")))
    for ready in deduper.flush():
        print(json.dumps(ready, separators=(",", ":")))
    return 0


def _doctor() -> int:
    executable = shutil.which("rtl_433") or "rtl_433"
    print(f"ism-scan {__version__}")
    print(f"rtl_433: {executable}")
    try:
        version = subprocess.run(
            [executable, "-V"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        detail = (version.stderr or version.stdout).strip().splitlines()
        print(f"rtl_433 version: {detail[0] if detail else 'unknown'}")
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"rtl_433 could not be executed: {error}")
        return 1
    try:
        listing = subprocess.run(
            ["system_profiler", "SPUSBDataType"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        blob = listing.stdout
        if "NESDR" in blob or "RTL2832" in blob or "0x2838" in blob:
            serial = re.search(r"Serial Number:\s*(\S+)", blob[blob.find("NESDR") :])
            print(
                "USB: NESDR / RTL2832-family receiver visible"
                + (f" (serial {serial.group(1)})" if serial else "")
            )
        else:
            print("USB: no obvious RTL-SDR in system_profiler output")
    except (OSError, subprocess.TimeoutExpired):
        print("USB: system_profiler unavailable")
    everything = procs.list_processes()
    owners = procs.rtl_433_owners(everything)
    servers = procs.serve_processes(everything)
    if owners:
        print(f"Radio: held by {len(owners)} rtl_433 process(es); only one may own the dongle")
        for proc in owners:
            print(f"  pid {proc.pid}: {proc.short}")
    else:
        print("Radio: no rtl_433 running; the dongle is free")
    if servers:
        print(f"Servers: {len(servers)} `ism-scan serve` running (use `ism-scan stop` to end)")
        for proc in servers:
            print(f"  pid {proc.pid}: {proc.short}")
    print(f"Default listen: 433.92M with analyser ({' '.join(DEFAULT_RTL_ARGS)})")
    print(f"Working directory: {Path.cwd()}")
    print(f"Python: {sys.version.split()[0]}  uid={os.getuid()}")
    print(f"Clock: {datetime.now(UTC).replace(microsecond=0).isoformat()}")
    return 0


def _stop() -> int:
    everything = procs.list_processes()
    servers = procs.serve_processes(everything)
    if not servers and not procs.rtl_433_owners(everything):
        print("Nothing to stop: no `ism-scan serve` or rtl_433 is running.")
        return 0
    for proc, result in procs.stop(servers):
        print(f"ism-scan serve pid {proc.pid}: {result}")
    # rtl_433 normally dies with its parent; only orphans need a separate nudge.
    for proc, result in procs.stop(procs.rtl_433_owners()):
        print(f"rtl_433 pid {proc.pid}: {result}")
    return 0


def _frequency(value: str) -> str:
    if not _FREQUENCY.match(value):
        raise argparse.ArgumentTypeError("expected a frequency such as 433.92M")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
