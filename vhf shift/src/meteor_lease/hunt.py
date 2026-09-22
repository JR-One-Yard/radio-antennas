from __future__ import annotations

import json
import shutil
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from meteor_lease.heard import icao_from_dump1090, icao_from_rtl_adsb_line, write_heard
from meteor_lease.paths import CAPTURES, VHF_ROOT
from meteor_lease.radio import _uv_env

HUNT_PID = VHF_ROOT / "captures" / "hunt.pid"
HEARD = CAPTURES / "heard"
SUMMARY = CAPTURES / "heard" / "SUMMARY.txt"


def _run(cmd: list[str], *, seconds: int, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        env=_uv_env(),
        check=False,
        capture_output=True,
        text=True,
        timeout=seconds + 8,
    )


def slice_planes(seconds: int = 40) -> dict:
    HEARD.mkdir(parents=True, exist_ok=True)
    json_dir = HEARD / "dump1090"
    json_dir.mkdir(parents=True, exist_ok=True)
    dump1090 = shutil.which("dump1090") or shutil.which("dump1090-fa")
    if dump1090:
        proc = subprocess.Popen(  # noqa: S603
            [dump1090, "--quiet", "--write-json", str(json_dir), "--write-json-every", "1"],
            env=_uv_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(seconds)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        aircraft_path = json_dir / "aircraft.json"
        rows = []
        if aircraft_path.is_file():
            try:
                rows = icao_from_dump1090(json.loads(aircraft_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                rows = []
        write_heard(HEARD / "planes.jsonl", "adsb", rows)
        return {"decoder": "dump1090", "count": len(rows), "planes": rows}

    rtl = shutil.which("rtl_adsb")
    if not rtl:
        return {"decoder": None, "count": 0, "planes": [], "error": "no dump1090 or rtl_adsb"}
    try:
        result = _run([rtl, "-V"], seconds=seconds)
    except subprocess.TimeoutExpired:
        return {"decoder": "rtl_adsb", "count": 0, "planes": [], "error": "timeout"}
    icaos: dict[str, int] = {}
    for line in (result.stdout or "").splitlines() + (result.stderr or "").splitlines():
        icao = icao_from_rtl_adsb_line(line)
        if icao:
            icaos[icao] = icaos.get(icao, 0) + 1
    rows = [{"hex": k, "frames": v} for k, v in sorted(icaos.items())]
    write_heard(HEARD / "planes.jsonl", "adsb", rows)
    return {"decoder": "rtl_adsb", "count": len(rows), "planes": rows}


def slice_ais_power(seconds: int = 12) -> dict:
    """No ship decoder on this Mac yet. Measure whether 162 MHz is even busy."""
    rtl_power = shutil.which("rtl_power")
    if not rtl_power:
        return {"decoder": None, "error": "no rtl_power"}
    csv = HEARD / "ais-power.csv"
    HEARD.mkdir(parents=True, exist_ok=True)
    try:
        result = _run(
            [
                rtl_power,
                "-f",
                "161.9M:162.1M:2500",
                "-i",
                str(max(2, seconds // 2)),
                "-1",
                str(csv),
            ],
            seconds=seconds + 5,
        )
    except subprocess.TimeoutExpired:
        return {"decoder": "rtl_power", "error": "timeout"}
    db = _max_db(csv)
    write_heard(
        HEARD / "ships.jsonl",
        "ais-power",
        [{"mhz": 162.0, "max_db": db, "note": "power only; no names without AIS-catcher"}],
    )
    return {
        "decoder": "rtl_power",
        "max_db": db,
        "stderr": (result.stderr or "")[-400:],
        "csv": str(csv),
    }


def slice_airband(seconds: int = 12) -> dict:
    """Sydney Approach North 124.4 MHz AM. Loudness only — no speech-to-text."""
    rtl_fm = shutil.which("rtl_fm")
    if not rtl_fm:
        return {"decoder": None, "error": "no rtl_fm"}
    HEARD.mkdir(parents=True, exist_ok=True)
    raw = HEARD / "airband-1244.raw"
    try:
        with raw.open("wb") as handle:
            subprocess.run(  # noqa: S603
                [rtl_fm, "-M", "am", "-f", "124.4M", "-s", "12000", "-g", "40", "-l", "0"],
                env=_uv_env(),
                stdout=handle,
                stderr=subprocess.DEVNULL,
                timeout=seconds,
                check=False,
            )
    except subprocess.TimeoutExpired:
        pass
    rms = _rms_u8(raw) if raw.is_file() else 0.0
    size = raw.stat().st_size if raw.is_file() else 0
    write_heard(
        HEARD / "airband.jsonl",
        "am",
        [{"mhz": 124.4, "label": "Sydney Approach North", "rms": rms, "bytes": size}],
    )
    return {"decoder": "rtl_fm", "mhz": 124.4, "rms": rms, "bytes": size}


def _max_db(csv: Path) -> float | None:
    if not csv.is_file():
        return None
    best: float | None = None
    for line in csv.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(",")
        for token in parts[6:]:
            try:
                value = float(token)
            except ValueError:
                continue
            if best is None or value > best:
                best = value
    return best


def _rms_u8(path: Path) -> float:
    data = path.read_bytes()
    if not data:
        return 0.0
    # rtl_fm raw is signed 16-bit little-endian
    import array

    samples = array.array("h")
    samples.frombytes(data[: len(data) - (len(data) % 2)])
    if not samples:
        return 0.0
    acc = sum(s * s for s in samples) / len(samples)
    return acc ** 0.5


def write_summary(chunks: list[dict]) -> Path:
    HEARD.mkdir(parents=True, exist_ok=True)
    planes = next((c for c in chunks if "planes" in c), {})
    n = planes.get("count", 0)
    lines = [
        f"Heard at {datetime.now().astimezone().strftime('%a %I:%M %p')}",
        f"Planes: {n}",
    ]
    for plane in (planes.get("planes") or [])[:12]:
        flight = plane.get("flight") or plane.get("hex")
        alt = plane.get("alt_ft")
        extra = f"  {alt} ft" if alt else ""
        lines.append(f"  - {flight}{extra}")
    ais = next((c for c in chunks if c.get("decoder") == "rtl_power"), {})
    if ais:
        lines.append(f"Ships: no names yet. Radio loudness near 162 MHz: {ais.get('max_db')} dB")
    air = next((c for c in chunks if c.get("mhz") == 124.4), {})
    if air:
        rms = air.get("rms")
        if rms is not None:
            lines.append(f"Sydney Approach 124.4: audio RMS {rms:.0f}")
        else:
            lines.append("airband: n/a")
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SUMMARY


def one_round(*, plane_s: int = 40, ais_s: int = 12, air_s: int = 10) -> list[dict]:
    chunks = [slice_planes(plane_s), slice_ais_power(ais_s), slice_airband(air_s)]
    write_summary(chunks)
    return chunks
