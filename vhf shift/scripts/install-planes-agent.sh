#!/bin/bash
# Install the always-on plane-map LaunchAgent for the logged-in Mini user.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.oneyard.planes"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
mkdir -p "${HOME}/Library/LaunchAgents" "$ROOT/captures"
chmod +x "$ROOT/scripts/yard-idle.sh" "$ROOT/scripts/meteor-pass.sh" "$ROOT/scripts/yard-mode.sh"

cat >"$DEST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${ROOT}/scripts/yard-idle.sh</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/captures/launchd-planes-out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/captures/launchd-planes-err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/bin:/bin:${HOME}/.local/bin</string>
  </dict>
</dict>
</plist>
EOF

uid="$(id -u)"
launchctl bootout "gui/${uid}" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/${uid}" "$DEST"
launchctl kickstart -k "gui/${uid}/${LABEL}"
# Something else may already own https://<radio-host>/ on 443. The map gets HTTPS on :10900 (tailnet only).
# Do not `tailscale serve reset` — that would drop whatever else is served on 443.
# Do not enable Funnel.
tailscale serve --bg --https=10900 http://127.0.0.1:10900
echo "loaded ${LABEL}"
echo "open https://<this-host>:10900/  (plain HTTP can fail if the browser has HSTS for this name)"
