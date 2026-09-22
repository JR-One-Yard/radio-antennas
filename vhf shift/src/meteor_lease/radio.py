from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from meteor_lease.paths import SATDUMP_APP, SCANNER_DIR

SATDUMP_NAMES = {"satdump", "satdump-ui", "SatDump", "satdump_sdr_server"}
# ism-scan doctor only sees rtl_433. dump1090 holding USB looks "free" without this.
SDR_HOLDERS = {"dump1090", "dump1090-fa", "rtl_fm", "rtl_sdr", "rtl_power", "rtl_adsb"}
DONGLE_FREE = "the dongle is free"
SERVE_RUNNING = "`ism-scan serve` running"
LIVE_URL = "http://127.0.0.1:4330/api/status"


@dataclass(frozen=True, slots=True)
class Snapshot:
    dongle_free: bool
    serve_running: bool
    satdump_running: bool
    usb_visible: bool
    text: str
    live: dict | None = None
    satdump_pids: tuple[int, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass
class FakeRadio:
    """In-memory radio for tests. Never talks to USB."""

    dongle_free: bool = True
    serve_running: bool = False
    satdump_running: bool = False
    usb_visible: bool = True
    live: dict | None = field(
        default_factory=lambda: {
            "state": "listening",
            "source": "rtl_433",
            "workaround": None,
            "health": "ok",
        }
    )
    stops: int = 0
    serves: int = 0
    log: list[str] = field(default_factory=list)

    def snapshot(self) -> Snapshot:
        text = _fake_doctor_text(self)
        return Snapshot(
            dongle_free=self.dongle_free and not self.satdump_running,
            serve_running=self.serve_running,
            satdump_running=self.satdump_running,
            usb_visible=self.usb_visible,
            text=text,
            live=self.live,
            satdump_pids=(4242,) if self.satdump_running else (),
        )

    def stop(self) -> str:
        self.stops += 1
        self.serve_running = False
        self.dongle_free = True
        self.log.append("stop")
        return "Nothing to stop: no `ism-scan serve` or rtl_433 is running.\n"

    def serve_live_only(self) -> None:
        self.serves += 1
        self.serve_running = True
        self.dongle_free = False
        self.live = {
            "state": "listening",
            "source": "rtl_433",
            "workaround": None,
            "health": "ok",
        }
        self.log.append("serve --live-only")

    def note(self, message: str) -> None:
        self.log.append(message)


def _fake_doctor_text(radio: FakeRadio) -> str:
    lines = ["ism-scan 0.1.0", "USB: NESDR / RTL2832-family receiver visible (serial unset)"]
    if radio.dongle_free:
        lines.append("Radio: no rtl_433 running; the dongle is free")
    else:
        lines.append("Radio: held by 1 rtl_433 process(es); only one may own the dongle")
        lines.append("  pid 9: rtl_433 -f 433.92M")
    if radio.serve_running:
        lines.append("Servers: 1 `ism-scan serve` running (use `ism-scan stop` to end)")
    return "\n".join(lines) + "\n"


class IsmScanRadio:
    """Shells out to the existing 433 scanner. Does not import it."""

    def __init__(self, scanner_dir: Path | None = None, *, status_url: str = LIVE_URL) -> None:
        self.scanner_dir = scanner_dir or SCANNER_DIR
        self.status_url = status_url

    def snapshot(self) -> Snapshot:
        text = self._ism("doctor")
        satdump_pids = _holder_pids(SATDUMP_NAMES)
        sdr_pids = _holder_pids(SDR_HOLDERS)
        return Snapshot(
            dongle_free=DONGLE_FREE in text and not satdump_pids and not sdr_pids,
            serve_running=SERVE_RUNNING in text,
            satdump_running=bool(satdump_pids),
            usb_visible="NESDR" in text or "RTL2832" in text,
            text=text,
            live=_fetch_status(self.status_url),
            satdump_pids=satdump_pids,
        )

    def stop(self) -> str:
        return self._ism("stop")

    def serve_live_only(self) -> None:
        log = self.scanner_dir / "captures" / "meteor-lease-serve.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as handle:
            subprocess.Popen(  # noqa: S603
                self._uv_prefix() + ["ism-scan", "serve", "--live-only"],
                cwd=self.scanner_dir,
                env=_uv_env(),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    def note(self, message: str) -> None:
        print(message)

    def _ism(self, *args: str) -> str:
        result = subprocess.run(  # noqa: S603
            self._uv_prefix() + ["ism-scan", *args],
            cwd=self.scanner_dir,
            env=_uv_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=40,
        )
        return (result.stdout or "") + (result.stderr or "")

    def _uv_prefix(self) -> list[str]:
        uv = shutil.which("uv") or "uv"
        return [uv, "run"]


def _uv_env() -> dict[str, str]:
    """Do not leak this project's venv into `uv run` for Over the Fence."""
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    return env


def find_satdump() -> Path | None:
    # Prefer the .app binary. The brew symlink made SatDump look for
    # /usr/local/share/satdump/satdump_cfg.json and die (5 Sep 2026).
    if SATDUMP_APP.is_file():
        return SATDUMP_APP
    which = shutil.which("satdump")
    return Path(which) if which else None


def _holder_pids(names: set[str]) -> tuple[int, ...]:
    if shutil.which("ps") is None:
        return ()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    found: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        first = os.path.basename(parts[1].split()[0])
        if first in names:
            found.append(int(parts[0]))
    return tuple(found)


def _satdump_pids() -> tuple[int, ...]:
    return _holder_pids(SATDUMP_NAMES)


def _fetch_status(url: str) -> dict | None:
    try:
        with urlopen(url, timeout=2) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def wait_until(predicate, *, timeout: float, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def listening_ok(live: dict | None) -> bool:
    if not live:
        return False
    if live.get("workaround") == "live-to-simulate-fallback":
        return False
    if live.get("source") == "simulate":
        return False
    return live.get("source") == "rtl_433" and live.get("state") in {"listening", "starting"}
