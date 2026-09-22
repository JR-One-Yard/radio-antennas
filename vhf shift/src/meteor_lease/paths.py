from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
VHF_ROOT = PACKAGE.parents[1]
REPO_ROOT = VHF_ROOT.parent
SCANNER_DIR = REPO_ROOT / "433 scanner"
CAPTURES = VHF_ROOT / "captures"
QTH_FILE = VHF_ROOT / "qth.json"
QTH_EXAMPLE = VHF_ROOT / "qth.example.json"
HOST_FILE = VHF_ROOT / "host.json"
HOST_EXAMPLE = VHF_ROOT / "host.example.json"
AUTOTRACK_EXAMPLE = VHF_ROOT / "satdump" / "autotrack.example.json"
STOLEN_FLAG = CAPTURES / "stick.stolen"
SATDUMP_APP = Path("/Applications/SatDump.app/Contents/MacOS/satdump")
