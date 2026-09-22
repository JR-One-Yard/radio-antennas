from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from meteor_lease.host import load_host
from meteor_lease.paths import STOLEN_FLAG

DUMP1090_NAMES = {"dump1090", "dump1090-fa"}


def steal() -> None:
    """Stop dump1090 / map HTTP so SatDump can own USB. LaunchAgent waits on this flag."""
    STOLEN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    STOLEN_FLAG.write_text("stolen\n", encoding="utf-8")
    _kill_named(DUMP1090_NAMES)
    _kill_cmd_substr("yard_http.py")


def giveback() -> None:
    STOLEN_FLAG.unlink(missing_ok=True)


def stolen() -> bool:
    return STOLEN_FLAG.is_file()


def dump1090_pids() -> tuple[int, ...]:
    return _pids(DUMP1090_NAMES)


def dump1090_running() -> bool:
    return bool(dump1090_pids())


def planes_ready() -> bool:
    if stolen():
        return False
    if load_host()["idle"] != "dump1090":
        return False
    return dump1090_running()


@dataclass
class FakeYard:
    """In-memory idle box for tests. Never kills processes."""

    idle: str = "ism-scan"
    is_stolen: bool = False
    dump1090: bool = False
    steals: int = 0
    givebacks: int = 0

    def steal(self) -> None:
        self.steals += 1
        self.is_stolen = True
        self.dump1090 = False

    def giveback(self) -> None:
        self.givebacks += 1
        self.is_stolen = False
        if self.idle == "dump1090":
            self.dump1090 = True

    def idle_name(self) -> str:
        return self.idle

    def planes_ready(self) -> bool:
        return self.idle == "dump1090" and self.dump1090 and not self.is_stolen


class LiveYard:
    def steal(self) -> None:
        steal()

    def giveback(self) -> None:
        giveback()

    def idle_name(self) -> str:
        return str(load_host()["idle"])

    def planes_ready(self) -> bool:
        return planes_ready()


def _pids(names: set[str]) -> tuple[int, ...]:
    found: list[int] = []
    for pid, command in _ps():
        first = os.path.basename(command.split()[0]) if command else ""
        if first in names:
            found.append(pid)
    return tuple(found)


def _kill_named(names: set[str]) -> None:
    for pid in _pids(names):
        _term(pid)


def _kill_cmd_substr(needle: str) -> None:
    for pid, command in _ps():
        if needle in command:
            _term(pid)


def _term(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _ps() -> list[tuple[int, str]]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        try:
            rows.append((int(parts[0]), parts[1]))
        except ValueError:
            continue
    return rows


def find_dump1090() -> Path | None:
    import shutil

    for name in ("dump1090", "dump1090-fa"):
        which = shutil.which(name)
        if which:
            return Path(which)
    return None
