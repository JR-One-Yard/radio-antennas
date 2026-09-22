"""Readonly checks against the live Over the Fence session. Never --commit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

VHF = Path(__file__).resolve().parents[1]


def _status() -> dict | None:
    try:
        with urlopen("http://127.0.0.1:4330/api/status", timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        return None


def test_dry_run_pass_does_not_steal_live_radio():
    before = _status()
    if before is None or before.get("source") != "rtl_433":
        return
    lines_before = int(before.get("raw_lines") or 0)
    result = subprocess.run(
        ["uv", "run", "meteor-lease", "pass", "--stub", "--yes"],
        cwd=VHF,
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "would run `ism-scan stop`" in result.stdout
    after = _status()
    assert after is not None
    assert after.get("source") == "rtl_433"
    assert after.get("workaround") != "live-to-simulate-fallback"
    assert int(after.get("raw_lines") or 0) >= lines_before


def test_doctor_sees_satdump_and_live_census():
    result = subprocess.run(
        ["uv", "run", "meteor-lease", "doctor"],
        cwd=VHF,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SatDump:" in result.stdout
    assert "dry-run" in result.stdout
