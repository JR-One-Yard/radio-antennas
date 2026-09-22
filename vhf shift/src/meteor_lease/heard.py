from __future__ import annotations

import json
import re
from pathlib import Path

_HEX = re.compile(r"^[0-9a-fA-F]{6}$")
_STAR = re.compile(r"\*([0-9a-fA-F]{14,})[;]?")


def icao_from_dump1090(aircraft_json: dict) -> list[dict]:
    rows = []
    for plane in aircraft_json.get("aircraft") or []:
        hex_id = str(plane.get("hex") or "").strip().lower()
        if not _HEX.match(hex_id):
            continue
        flight = str(plane.get("flight") or "").strip() or None
        rows.append(
            {
                "hex": hex_id,
                "flight": flight,
                "alt_ft": plane.get("alt_baro") or plane.get("alt_geom"),
                "speed": plane.get("gs"),
                "lat": plane.get("lat"),
                "lon": plane.get("lon"),
                "seen": plane.get("seen"),
            }
        )
    return rows


def icao_from_rtl_adsb_line(line: str) -> str | None:
    match = _STAR.search(line)
    if not match:
        return None
    payload = match.group(1)
    if len(payload) < 8:
        return None
    return payload[2:8].lower()


def write_heard(path: Path, kind: str, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({"kind": kind, **row}, separators=(",", ":")) + "\n")
