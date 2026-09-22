from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from meteor_lease.idle import LiveYard
from meteor_lease.png import write_mock_strip
from meteor_lease.radio import Snapshot, listening_ok, wait_until

Prompt = Callable[[str], None]


class LeaseError(RuntimeError):
    pass


def acquire(
    radio,
    *,
    commit: bool,
    yes: bool,
    prompt: Prompt,
    yard=None,
) -> Snapshot:
    yard = yard or LiveYard()
    if not yes:
        if yard.idle_name() == "dump1090":
            prompt("Telescopic should already be on. NESDR will leave the plane map for one pass.")
        else:
            prompt(
                "Screw off the long black 433 whip. "
                "Set the telescopic mast as a shallow V (~120°), each arm ~54.5 cm, roughly N–S."
            )
    if not commit:
        radio.note("dry-run: would stop the idle occupant and wait until the dongle is free")
        return radio.snapshot()
    radio.stop()
    yard.steal()
    if not wait_until(lambda: radio.snapshot().dongle_free, timeout=20):
        raise LeaseError("dongle still held after idle stop")
    return radio.snapshot()


def release(
    radio,
    *,
    commit: bool,
    yes: bool,
    prompt: Prompt,
    yard=None,
) -> Snapshot:
    yard = yard or LiveYard()
    if not yes:
        if yard.idle_name() == "dump1090":
            prompt("Quit SatDump if it is still open. Plane map will take the stick back.")
        else:
            prompt("Quit SatDump if it is still open. Screw the long black 433 whip back on.")
    if not commit:
        if yard.idle_name() == "dump1090":
            radio.note("dry-run: would give the stick back to dump1090")
        else:
            radio.note("dry-run: would start `ism-scan serve --live-only` and wait for live RF")
        return radio.snapshot()
    if radio.snapshot().satdump_running:
        raise LeaseError("SatDump still holds the radio; quit it before handing back")
    if yard.idle_name() == "dump1090":
        yard.giveback()
        if not wait_until(yard.planes_ready, timeout=25):
            raise LeaseError("dump1090 did not come back after the pass")
        return radio.snapshot()
    yard.giveback()
    radio.serve_live_only()
    if not wait_until(lambda: listening_ok(radio.snapshot().live), timeout=25):
        snap = radio.snapshot()
        raise LeaseError(f"Over the Fence did not come back live: {snap.live}")
    return radio.snapshot()


def stub_pass(dest: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    png = dest / f"{stamp}_stub_meteor_m2-x_lrpt" / "MSU-MR" / "msu_mr_rgb_MSA_corrected.png"
    write_mock_strip(png)
    return png


def satdump_recipe(*, satdump: Path | None) -> str:
    binary = str(satdump) if satdump else "satdump (not on PATH)"
    return (
        "Attended SatDump pass (you run this; the lease does not own the PHY):\n"
        f"  binary: {binary}\n"
        "  GUI: open SatDump → Recorder → pipeline meteor_m2-x_lrpt (72k)\n"
        "  frequency 137.9 MHz (if no lock: 137.1 MHz, or 80k pipeline)\n"
        "  bias tee OFF, AGC OFF, manual gain high, 1.024 or 2.048 MS/s\n"
        "  watch the strip paint; Stop the device at LOS; quit SatDump completely\n"
        "  product: MSU-MR/msu_mr_rgb_*.png in the live output folder\n"
        "Do not leave SatDump running. It will take the dongle at the next AOS.\n"
        "Always use /Applications/SatDump.app/Contents/MacOS/satdump — not the brew symlink."
    )


def idle_handback_ok(after: Snapshot, yard=None) -> bool:
    yard = yard or LiveYard()
    if yard.idle_name() == "dump1090":
        return yard.planes_ready()
    return listening_ok(after.live)
