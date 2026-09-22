# Operator checklist — satellite morning

Idle occupant depends on the mast (`host.json`). Telescopic → dump1090 / plane map. Black whip → Over the Fence `--live-only`.

## Telescopic (radio host)

1. `uv run meteor-lease doctor` — idle dump1090, SatDump is the **.app** binary, QTH filled if you care about pass times.
2. Predict Meteor-M2-4 (NORAD 59051), max elevation ≥ 20°. Skip low ones.
3. `scripts/meteor-pass.sh` on the radio host, or `uv run meteor-lease pass --decoder satdump --yes --commit` and follow the printed recipe.
4. SatDump must quit. Empty CADU / no `msu_mr_rgb_*.png` is not a picture.
5. Stick goes back to dump1090. Open the Tailscale plane map (`meteor-lease doctor` prints the URL). Captures: `http://<radio-host>:10900/captures/`.

If you abort after `--commit`, run `uv run meteor-lease release --yes --commit` so dump1090 is not left dead.

## 433 whip (later)

Physical swap first, then `scripts/yard-mode.sh whip`. Confirm `/api/status` is `source: rtl_433`, not the demo neighbourhood.

1. `uv run meteor-lease doctor`
2. Swap to telescopic for the pass (or skip the pass).
3. `uv run meteor-lease pass --decoder satdump --yes --commit`
4. Whip back on, handback starts `ism-scan serve --live-only`.

Never leave SatDump open. Never start SatDump while dump1090 or `ism-scan serve` still holds USB. Never `satdump autotrack` 24/7.
