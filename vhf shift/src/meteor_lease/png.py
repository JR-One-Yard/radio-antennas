from __future__ import annotations

import json
from pathlib import Path


def write_mock_strip(path: Path, *, width: int = 480, height: int = 160) -> Path:
    """A fake Meteor colour composite so unsupervised runs still produce a PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            # Soft "ocean / land / cloud" so Preview shows a strip, not a blank.
            land = x + y * 2 > width + 40 and x + y * 2 < width * 2 - 80
            cloud = ((x * 13 + y * 7) % 97) > 78 or ((x - 240) ** 2 + (y - 50) ** 2) < 900
            if cloud:
                row.extend((228, 230, 236))
            elif land:
                row.extend((46, 92, 58))
            else:
                row.extend((18, 42, 96))
        rows.append(bytes(row))
    path.write_bytes(_png_rgb(width, height, rows))
    return path


def _png_rgb(width: int, height: int, rows: list[bytes]) -> bytes:
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + row for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def load_qth(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    lat, lon = data.get("lat"), data.get("lon")
    if lat is None or lon is None:
        return None
    return data
