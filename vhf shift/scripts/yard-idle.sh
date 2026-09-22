#!/bin/bash
# Idle occupant for the yard NESDR when the telescopic is on: dump1090 + Tailscale map.
# LaunchAgent runs `run`. meteor-lease steal/giveback uses the stick.stolen flag.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"
HOST="$ROOT/host.json"
STOLEN="$ROOT/captures/stick.stolen"
JSON="$ROOT/captures/heard/dump1090"
HTTP="$ROOT/scripts/yard_http.py"
WEB="$ROOT/web/planes/index.html"
LOG="$ROOT/captures/yard-idle.log"

mkdir -p "$JSON" "$ROOT/captures"
QTH="$ROOT/qth.json"

install_map() {
  /usr/bin/python3 - "$WEB" "$JSON/index.html" "$QTH" <<'PY'
import json, re, sys
from pathlib import Path
src, dest, qth_path = map(Path, sys.argv[1:4])
html = src.read_text(encoding="utf-8")
if qth_path.is_file():
    try:
        qth = json.loads(qth_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        qth = {}
    lat, lon = qth.get("lat"), qth.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        html, n = re.subn(
            r"setView\(\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]",
            f"setView([{lat}, {lon}]",
            html,
            count=1,
        )
        if n != 1:
            print("map qth inject missed setView", file=sys.stderr)
dest.write_text(html, encoding="utf-8")
PY
}

idle() {
  python3 -c "import json,sys; p=sys.argv[1]
print(json.load(open(p)).get('idle','dump1090') if __import__('os').path.isfile(p) else 'dump1090')" "$HOST"
}

serial() {
  python3 -c "import json,sys; p=sys.argv[1]
print(json.load(open(p)).get('device_serial','') if __import__('os').path.isfile(p) else '')" "$HOST"
}

port() {
  python3 -c "import json,sys; p=sys.argv[1]
print(json.load(open(p)).get('planes_port',10900) if __import__('os').path.isfile(p) else 10900)" "$HOST"
}

bind_addr() {
  python3 - "$ROOT" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
host_path = root / "host.json"
host = json.loads(host_path.read_text()) if host_path.is_file() else {}
bind = str(host.get("bind") or "127.0.0.1")
if bind in {"0.0.0.0", "::", "*"}:
    raise SystemExit("refusing public bind")
if bind in {"tailscale", "magicdns"}:
    for cand in (
        shutil.which("tailscale"),
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ):
        if not cand:
            continue
        try:
            out = subprocess.check_output([cand, "ip", "-4"], text=True, timeout=5)
        except Exception:
            continue
        ip = out.strip().split()[0]
        if ip.startswith("100."):
            print(ip)
            raise SystemExit(0)
    raise SystemExit("no tailscale ipv4")
print(bind)
PY
}

dump1090_bin() {
  command -v dump1090 || command -v dump1090-fa
}

cmd="${1:-run}"
case "$cmd" in
  steal)
    echo stolen > "$STOLEN"
    pkill -x dump1090 2>/dev/null || true
    pkill -x dump1090-fa 2>/dev/null || true
    pkill -f yard_http.py 2>/dev/null || true
    ;;
  giveback)
    rm -f "$STOLEN"
    ;;
  status)
    echo "idle=$(idle) stolen=$( [[ -f $STOLEN ]] && echo yes || echo no )"
    bind_addr || true
    ;;
  run)
    exec >>"$LOG" 2>&1
    echo "=== yard-idle run $(date) ==="
    install_map
    DUMP="$(dump1090_bin)" || { echo "dump1090 not installed"; exit 1; }
    while true; do
      if [[ "$(idle)" != "dump1090" ]]; then
        sleep 5
        continue
      fi
      if [[ -f "$STOLEN" ]]; then
        sleep 2
        continue
      fi
      if ! BIND="$(bind_addr)"; then
        echo "waiting for Tailscale bind"
        sleep 5
        continue
      fi
      PORT="$(port)"
      SERIAL="$(serial)"
      install_map
      if [[ -n "$SERIAL" ]]; then
        "$DUMP" --quiet --write-json "$JSON" --write-json-every 1 --device "$SERIAL" &
      else
        "$DUMP" --quiet --write-json "$JSON" --write-json-every 1 &
      fi
      dpid=$!
      # Homebrew Python is blocked by Application Firewall; CLT python is allowed.
      /usr/bin/python3 "$HTTP" --bind "$BIND" --port "$PORT" --planes "$JSON" --captures "$ROOT/captures" &
      hpid=$!
      wait "$dpid" || true
      kill "$hpid" 2>/dev/null || true
      wait "$hpid" 2>/dev/null || true
      sleep 1
    done
    ;;
  *)
    echo "usage: $0 run|steal|giveback|status" >&2
    exit 2
    ;;
esac
