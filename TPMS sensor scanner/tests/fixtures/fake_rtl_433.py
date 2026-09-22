#!/usr/bin/env python3
import json
import sys
import time


def value_after(flag: str) -> str | None:
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


if "-q" in sys.argv:
    print("fake receiver failure", file=sys.stderr)
    raise SystemExit(7)

event = {
    "type": "TPMS",
    "model": "Fake TPMS",
    "id": "FAKE0001",
    "pressure_kPa": 215,
    "_received_frequency": value_after("-f"),
    "_received_format": value_after("-F"),
    "_received_meta": value_after("-M"),
}
print(json.dumps(event), flush=True)

if "-G" in sys.argv:
    time.sleep(30)
