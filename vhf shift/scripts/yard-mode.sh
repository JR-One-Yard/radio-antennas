#!/bin/bash
# Flip idle occupant after a physical mast swap. Same NESDR, no second dongle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"
HOST="$ROOT/host.json"
MODE="${1:-}"

if [[ ! -f "$HOST" ]]; then
  cp "$ROOT/host.example.json" "$HOST"
fi

bind_ip() {
  python3 - "$ROOT" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
host = json.loads((root / "host.json").read_text())
bind = str(host.get("bind") or "tailscale")
if bind in {"tailscale", "magicdns"}:
    for cand in (shutil.which("tailscale"), "/opt/homebrew/bin/tailscale", "/usr/local/bin/tailscale"):
        if cand:
            try:
                ip = subprocess.check_output([cand, "ip", "-4"], text=True, timeout=5).strip().split()[0]
            except Exception:
                continue
            if ip.startswith("100."):
                print(ip)
                raise SystemExit(0)
    raise SystemExit("no tailscale ip")
print(bind)
PY
}

write_idle() {
  python3 - "$HOST" "$1" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
idle = sys.argv[2]
data = json.loads(path.read_text()) if path.is_file() else {}
data["idle"] = idle
path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

case "$MODE" in
  telescopic|dump1090)
    echo "Expect the bundled telescopic on the NESDR."
    uv -q run --directory "$ROOT/../433 scanner" ism-scan stop 2>/dev/null || true
    write_idle dump1090
    rm -f "$ROOT/captures/stick.stolen"
    echo "idle=dump1090. Plane map LaunchAgent should take USB. Do not start ism-scan."
    ;;
  whip|433|ism-scan)
    echo "Expect the long black ~27 cm 433 whip on the NESDR."
    "$ROOT/scripts/yard-idle.sh" steal || true
    write_idle ism-scan
    BIND="$(bind_ip)"
    PORT="$(python3 -c "import json; print(json.load(open('$HOST')).get('census_port',4330))")"
    cd "$ROOT/../433 scanner"
    unset VIRTUAL_ENV UV_PROJECT UV_PROJECT_ENVIRONMENT
    nohup uv run ism-scan serve --live-only --host "$BIND" --port "$PORT" \
      >>"$ROOT/captures/ism-scan-serve.log" 2>&1 &
    echo "idle=ism-scan on $BIND:$PORT --live-only. Confirm source: rtl_433, not simulate."
    ;;
  *)
    echo "usage: $0 telescopic|whip" >&2
    echo "Physical swap first. This only flips software." >&2
    exit 2
    ;;
esac
