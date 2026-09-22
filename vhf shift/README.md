# Satellite morning

Steal the NESDR for one Meteor pass. Keep a **PNG weather strip**. Give the radio back.

This is receive-only. It does not transmit.

On the radio host (telescopic on the stick) the idle occupant is **dump1090**, not Over the Fence. Open the plane map from your laptop over Tailscale. The black 433 whip can be screwed back on later — same box, same stick, `scripts/yard-mode.sh whip`.

## What you get

A colour PNG (`msu_mr_rgb_*.png`): a long strip of Earth, about 1 km per pixel, ~2800 km wide. Coast and clouds. Not your street.

A stub pass writes a fake PNG so you can see the folder layout without waiting for a satellite.

## Do not steal the radio by accident

`meteor-lease` is **dry-run unless you pass `--commit`**. Idle occupant comes from `host.json` (`dump1090` or `ism-scan`). Copy `host.example.json` on the radio host.

```bash
cd "vhf shift"
uv sync --dev
uv run meteor-lease doctor
uv run meteor-lease pass --stub --yes
```

When you mean it — ≥20° Meteor-M2-4, telescopic already on:

```bash
uv run meteor-lease pass --decoder satdump --yes --commit
```

Or on the radio host: `scripts/meteor-pass.sh` (uses `/Applications/SatDump.app/Contents/MacOS/satdump`, then hands back to dump1090).

Do **not** start `ism-scan` on the telescopic and call hiss a neighbourhood. Use `--live-only` only after the black whip is on.

## Mast

- Now: telescopic **shallow V ~120°**, each arm **~54.5 cm**, roughly N–S
- Later, interchangeable: long black ~27 cm 433 whip (`scripts/yard-mode.sh whip`)
- Physical swap is minutes. No second dongle.

## SatDump

Always `/Applications/SatDump.app/Contents/MacOS/satdump`. The brew symlink died on 5 Sep 2026 looking for `/usr/local/share/satdump/satdump_cfg.json`. Bias tee **off**. 137.9 MHz, `meteor_m2-x_lrpt`. Skip passes under ~20°. Prefer Meteor-M N2-4 (NORAD 59051). Do not leave `satdump autotrack` running.

Copy `qth.example.json` to `qth.json` and fill lat/lon before you care about AOS times. Do not invent a surveyed roof.

## Hardware

Nooelec NESDR SMArt v5. Set the USB serial from `rtl_test` in `host.json`. No bias-T. One USB owner.

See `docs/OPERATOR.md` and `docs/WORKAROUNDS.md`.
