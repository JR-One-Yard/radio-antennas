"""Who else is holding the radio?

Only one process may open the RTL-SDR. ``rtl_433`` fails with
``usb_claim_interface error -6`` if another copy already has it, and this app
then silently falls back to the simulator. These helpers make that visible.

They also give ``ism-scan stop`` a way to end a stray server without the
classic footgun: ``pkill -f "ism-scan serve"`` matches the *shell* that typed
it, because that shell's command line contains the same string.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass

_SERVE = re.compile(r"(^|[/\s])ism-scan(\.exe)?\s+serve(\s|$)")
# A real launcher somewhere on the line (paths may contain spaces, so we cannot
# trust "the first token" to be the executable).
_LAUNCHER = re.compile(r"(^|[/\s])(python[\d.]*|ism-scan|uv|uvx)(\.exe)?\s")
# Things that merely *mention* the words: shells, searchers, this tool.
_NOT_LAUNCHERS = {
    "sh", "zsh", "bash", "fish", "dash", "ksh", "login", "script",
    "grep", "rg", "pgrep", "pkill", "ps", "tail", "less", "more", "cat",
    "vim", "vi", "nano", "code", "cursor",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Proc:
    pid: int
    ppid: int
    command: str

    @property
    def short(self) -> str:
        return self.command if len(self.command) <= 90 else self.command[:87] + "..."


def list_processes() -> list[Proc]:
    if shutil.which("ps") is None:
        return []
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    procs: list[Proc] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            procs.append(Proc(int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            continue
    return procs


def rtl_433_owners(procs: list[Proc] | None = None) -> list[Proc]:
    """rtl_433 binaries actually running (not shells that merely mention them)."""
    owners = []
    for proc in procs if procs is not None else list_processes():
        first = proc.command.split()[0] if proc.command.split() else ""
        if os.path.basename(first) in {"rtl_433", "rtl_433.exe"}:
            owners.append(proc)
    return owners


def serve_processes(
    procs: list[Proc] | None = None,
    *,
    exclude: set[int] | None = None,
) -> list[Proc]:
    """`ism-scan serve` launchers only: the python/uv binary, never a shell whose
    command line happens to contain the words."""
    listing = procs if procs is not None else list_processes()
    skip = set(exclude or ()) | ancestors(os.getpid(), listing) | {os.getpid()}
    found = []
    for proc in listing:
        if proc.pid in skip:
            continue
        tokens = proc.command.split()
        if not tokens:
            continue
        first = os.path.basename(tokens[0]).lstrip("-")
        if first in _NOT_LAUNCHERS:
            continue
        serve = _SERVE.search(proc.command)
        if serve and _LAUNCHER.search(proc.command[: serve.end()]):
            found.append(proc)
    # `uv run ism-scan serve` spawns the python launcher as a child; report the
    # root of each such chain once. Signalling the root takes the child with it.
    pids = {proc.pid for proc in found}
    return [proc for proc in found if proc.ppid not in pids]


def ancestors(pid: int, procs: list[Proc]) -> set[int]:
    parents = {proc.pid: proc.ppid for proc in procs}
    seen: set[int] = set()
    while pid in parents and pid not in seen and pid > 1:
        seen.add(pid)
        pid = parents[pid]
    return seen


def stop(procs: list[Proc], *, grace: float = 3.0) -> list[tuple[Proc, str]]:
    outcome: list[tuple[Proc, str]] = []
    for proc in procs:
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            outcome.append((proc, "already gone"))
            continue
        except PermissionError:
            outcome.append((proc, "not permitted"))
            continue
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and _alive(proc.pid):
            time.sleep(0.1)
        if _alive(proc.pid):
            try:
                os.kill(proc.pid, signal.SIGKILL)
                outcome.append((proc, "killed"))
            except OSError:
                outcome.append((proc, "would not die"))
        else:
            outcome.append((proc, "stopped"))
    return outcome


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
