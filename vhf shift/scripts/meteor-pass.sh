#!/bin/bash
# One Meteor listen on the Mini, then give the stick back to the idle occupant.
# Uses the SatDump .app binary (brew symlink dies looking for satdump_cfg.json).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"
unset VIRTUAL_ENV UV_PROJECT UV_PROJECT_ENVIRONMENT
SATDUMP="/Applications/SatDump.app/Contents/MacOS/satdump"
LOG="$ROOT/captures/meteor-pass.log"
mkdir -p "$ROOT/captures"
{
  echo "=== $(date) meteor-pass start timeout=${METEOR_TIMEOUT:-960} ==="
  if [[ ! -x "$SATDUMP" ]]; then
    echo "missing $SATDUMP"
    exit 1
  fi
  "$ROOT/scripts/yard-idle.sh" steal || true
  cd "$ROOT"
  uv run meteor-lease acquire --yes --commit
  OUT="$ROOT/captures/meteor-$(date -u +%Y%m%dT%H%MZ)"
  mkdir -p "$OUT"
  TIMEOUT="${METEOR_TIMEOUT:-960}"
  "$SATDUMP" live meteor_m2-x_lrpt "$OUT" \
    --source rtlsdr \
    --samplerate 1.024e6 \
    --frequency 137.9e6 \
    --gain 40 \
    --timeout "$TIMEOUT" \
    --dc_block \
    || echo "satdump exited $?"
  pkill -x satdump 2>/dev/null || true
  pkill -x satdump-ui 2>/dev/null || true
  sleep 2
  uv run meteor-lease release --yes --commit || echo "release failed $?"
  PNG="$(find "$OUT" -name 'msu_mr_rgb*.png' 2>/dev/null | head -1 || true)"
  echo "png=${PNG:-none}"
  if [[ -z "${PNG:-}" ]]; then
    echo "empty CADU is not a picture"
  fi
  echo "=== meteor-pass done ==="
} >>"$LOG" 2>&1
