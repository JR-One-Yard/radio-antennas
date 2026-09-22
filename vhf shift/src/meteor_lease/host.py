from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from meteor_lease.paths import HOST_EXAMPLE, HOST_FILE

DEFAULTS = {
    "idle": "ism-scan",
    "bind": "127.0.0.1",
    "planes_port": 10900,
    "census_port": 4330,
    "device_serial": "",
}


def load_host(path: Path | None = None) -> dict:
    """Idle occupant for this box. Missing file keeps laptop/433 defaults."""
    data = dict(DEFAULTS)
    target = path or HOST_FILE
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            data.update({k: loaded[k] for k in loaded if k in DEFAULTS or k == "note"})
    idle = data.get("idle")
    if idle not in {"dump1090", "ism-scan"}:
        data["idle"] = "ism-scan"
    else:
        data["idle"] = idle
    data["planes_port"] = int(data.get("planes_port") or 10900)
    data["census_port"] = int(data.get("census_port") or 4330)
    data["device_serial"] = str(data.get("device_serial") or "")
    data["bind"] = str(data.get("bind") or "127.0.0.1")
    data["example"] = str(HOST_EXAMPLE)
    return data


def resolve_bind(host: dict | None = None) -> str:
    host = host or load_host()
    bind = str(host.get("bind") or "127.0.0.1").strip()
    if bind in {"0.0.0.0", "::", "*", "localhost"}:
        if bind == "localhost":
            return "127.0.0.1"
        raise ValueError("refusing to bind all interfaces; use a Tailscale IP or 'tailscale'")
    if bind in {"tailscale", "magicdns"}:
        return _tailscale_ipv4() or "127.0.0.1"
    return bind


def _tailscale_ipv4() -> str | None:
    candidates = [
        shutil.which("tailscale"),
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ]
    for binary in candidates:
        if not binary:
            continue
        path = Path(binary)
        if not path.is_file():
            continue
        try:
            result = subprocess.run(  # noqa: S603
                [str(path), "ip", "-4"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        ip = (result.stdout or "").strip().split()[0] if result.stdout else ""
        if ip.startswith("100."):
            return ip
    return None


def census_status_url(host: dict | None = None) -> str:
    host = host or load_host()
    return f"http://{resolve_bind(host)}:{host['census_port']}/api/status"


def planes_url(host: dict | None = None) -> str:
    """Plane-map URL. When MagicDNS is up, the map is HTTPS on that name."""
    host = host or load_host()
    port = host["planes_port"]
    dns = _tailscale_dns()
    if dns:
        return f"https://{dns}:{port}/"
    bind = resolve_bind(host)
    scheme = "https" if bind == "127.0.0.1" else "http"
    return f"{scheme}://{bind}:{port}/"


def _tailscale_dns() -> str | None:
    candidates = [
        shutil.which("tailscale"),
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ]
    for binary in candidates:
        if not binary:
            continue
        path = Path(binary)
        if not path.is_file():
            continue
        try:
            result = subprocess.run(  # noqa: S603
                [str(path), "status", "--json"],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            continue
        name = str((payload.get("Self") or {}).get("DNSName") or "").rstrip(".")
        if name:
            return name
    return None
