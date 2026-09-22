#!/bin/bash
# Keep dump1090 on so the plane map stays live until the satellite steal.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JSON="$ROOT/captures/heard/dump1090"
STOP_AT="15:10"
export PATH="/opt/homebrew/bin:/usr/bin:/bin"
mkdir -p "$JSON"
cp "$ROOT/web/planes/index.html" "$JSON/index.html"
echo $$ > "$ROOT/captures/planes-ui.pid"
cd "$JSON"
exec /opt/homebrew/bin/dump1090 --quiet --write-json "$JSON" --write-json-every 1
