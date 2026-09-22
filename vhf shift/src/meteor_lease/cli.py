from __future__ import annotations

import argparse
import json
import sys

from meteor_lease import __version__
from meteor_lease.host import census_status_url, load_host, planes_url, resolve_bind
from meteor_lease.hunt import one_round, write_summary
from meteor_lease.idle import LiveYard, dump1090_running, find_dump1090, stolen
from meteor_lease.lease import (
    LeaseError,
    acquire,
    idle_handback_ok,
    release,
    satdump_recipe,
    stub_pass,
)
from meteor_lease.paths import (
    CAPTURES,
    HOST_FILE,
    QTH_EXAMPLE,
    QTH_FILE,
    SATDUMP_APP,
    SCANNER_DIR,
    VHF_ROOT,
)
from meteor_lease.png import load_qth
from meteor_lease.radio import IsmScanRadio, find_satdump, listening_ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meteor-lease",
        description="Steal the NESDR for one Meteor weather picture, then give it back.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="433 radio, SatDump, QTH, idle occupant — read-only")

    acquire_p = commands.add_parser(
        "acquire", help="stop the idle occupant and wait for a free dongle"
    )
    _lease_flags(acquire_p)

    release_p = commands.add_parser("release", help="start the idle occupant again")
    _lease_flags(release_p)

    pass_p = commands.add_parser("pass", help="acquire, decode (stub or SatDump), hand back")
    _lease_flags(pass_p)
    pass_p.add_argument(
        "--decoder",
        choices=("stub", "satdump"),
        default="stub",
        help="stub writes a mock PNG (default). satdump prints the attended recipe",
    )
    pass_p.add_argument("--stub", action="store_true", help="same as --decoder stub")

    hunt_p = commands.add_parser("hunt", help="listen for planes, then ships, then voices")
    _lease_flags(hunt_p)
    hunt_p.add_argument("--seconds", type=int, default=40, help="how long to listen for planes")
    return parser


def _lease_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually stop/start the idle occupant (default is dry-run)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip mast-swap prompts",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    host = load_host()
    radio = IsmScanRadio(status_url=census_status_url(host))
    yard = LiveYard()
    prompt = _prompt if not getattr(args, "yes", True) else (lambda _m: None)
    if args.command == "doctor":
        return _doctor(radio, host)
    try:
        if args.command == "acquire":
            acquire(radio, commit=args.commit, yes=args.yes, prompt=prompt, yard=yard)
            print("Dongle is yours for the pass." if args.commit else "Dry-run acquire finished.")
            return 0
        if args.command == "release":
            release(radio, commit=args.commit, yes=args.yes, prompt=prompt, yard=yard)
            print(_handback_line(host))
            return 0
        if args.command == "hunt":
            return _hunt(radio, args, prompt, yard)
        return _pass(radio, args, prompt, yard, host)
    except LeaseError as error:
        print(f"lease failed: {error}", file=sys.stderr)
        return 1


def _prompt(message: str) -> None:
    print(message)
    input("Press Enter when done. ")


def _handback_line(host: dict) -> str:
    if host["idle"] == "dump1090":
        return f"Plane map should be live at {planes_url(host)}"
    bind = resolve_bind(host)
    return f"Over the Fence should be live at http://{bind}:{host['census_port']}/"


def _doctor(radio: IsmScanRadio, host: dict) -> int:
    snap = radio.snapshot()
    print(f"meteor-lease {__version__}")
    print(f"vhf root: {VHF_ROOT}")
    print(f"433 scanner: {SCANNER_DIR} {'(present)' if SCANNER_DIR.is_dir() else '(MISSING)'}")
    print(f"host.json: {HOST_FILE} {'(present)' if HOST_FILE.is_file() else '(absent — defaults)'}")
    print(f"idle: {host['idle']}  bind: {resolve_bind(host)}  stolen: {stolen()}")
    satdump = find_satdump()
    print(f"SatDump: {satdump or 'not found — brew install --cask satdump'}")
    if satdump and satdump != SATDUMP_APP:
        print(f"WARNING: use {SATDUMP_APP} so config is found (brew symlink died on 5 Sep 2026)")
    dump1090 = find_dump1090()
    print(f"dump1090: {dump1090 or 'not found'}")
    qth = load_qth(QTH_FILE)
    if qth:
        print(f"QTH: {qth.get('lat')}, {qth.get('lon')} alt {qth.get('alt_m', '?')} m")
    else:
        print(f"QTH: unset — copy {QTH_EXAMPLE.name} to qth.json and fill lat/lon")
    print("--- ism-scan doctor ---")
    print(snap.text.rstrip())
    print("---")
    if snap.satdump_running:
        print(f"SatDump processes still running: pids {', '.join(map(str, snap.satdump_pids))}")
    else:
        print("SatDump: not running")
    print(f"dump1090 running: {dump1090_running()}")
    if snap.live:
        keys = ("state", "source", "health", "workaround", "raw_lines")
        print(f"Over the Fence: {json.dumps({k: snap.live.get(k) for k in keys})}")
        print("live RF" if listening_ok(snap.live) else "NOT live RF (simulator or down)")
    else:
        print(f"Over the Fence: nothing at {census_status_url(host)}")
    if host["idle"] == "dump1090":
        print(f"Plane map: {planes_url(host)}")
    print("Lease default is dry-run. Pass --commit only when you mean to steal the dongle.")
    return 0


def _hunt(radio, args, prompt, yard) -> int:
    acquire(radio, commit=args.commit, yes=args.yes, prompt=prompt, yard=yard)
    if not args.commit:
        print("Dry-run hunt: would listen for planes, then 162 MHz, then 124.4 MHz.")
        return 0
    chunks = one_round(plane_s=args.seconds, ais_s=12, air_s=10)
    summary = write_summary(chunks)
    print(summary.read_text(encoding="utf-8"))
    print(f"Wrote {summary}")
    return 0


def _pass(radio, args, prompt, yard, host) -> int:
    decoder = "stub" if args.stub else args.decoder
    acquire(radio, commit=args.commit, yes=args.yes, prompt=prompt, yard=yard)
    if decoder == "stub":
        png = stub_pass(CAPTURES)
        print(f"Stub postcard written (not a real satellite): {png}")
        print(
            "Open that PNG in Preview. A real pass uses "
            "--decoder satdump --commit after a ≥20° Meteor-M2-4 AOS."
        )
    else:
        print(satdump_recipe(satdump=find_satdump()))
        if not args.yes:
            prompt("When the PNG is written and SatDump has quit, continue.")
    after = release(radio, commit=args.commit, yes=args.yes, prompt=prompt, yard=yard)
    if args.commit and not idle_handback_ok(after, yard):
        print("Handback did not look live. Check `uv run meteor-lease doctor`.", file=sys.stderr)
        return 1
    if args.commit:
        print(_handback_line(host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
