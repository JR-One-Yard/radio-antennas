# Over the Fence

A 433 MHz neighbourhood census. It shows **everything** `rtl_433` can decode on the ISM mast, plus unmatched bursts the pulse analyser hears, then names each identity as well as the catalogue allows.

This is receive-only. It does not transmit, clone remotes, or store a database.

## Quick start

Plug in the NESDR SMArt v5. Screw the **long black 433 MHz mast** into the magnetic base.

```bash
cd "433 scanner"
uv sync --dev
uv run ism-scan doctor     # rtl_433 version, USB serial, who holds the radio
uv run ism-scan serve
```

Open [http://127.0.0.1:4330/](http://127.0.0.1:4330/).

If the radio cannot be opened, the UI falls back to a paced demo neighbourhood unless you pass `--live-only`. Only one process may own the dongle; `uv run ism-scan stop` ends a stray server by pid (safer than `pkill -f`, which matches the shell you typed it in).

```bash
uv run ism-scan simulate
uv run ism-scan replay examples/live-first-hear.jsonl
uv run ism-scan serve --capture captures/tonight.jsonl   # optional raw log, replayable, gitignored
```

## What you are looking at

- **Headline**: the most recent weather station, read as conditions (temperature, humidity, rain), with a temperature sparkline once it has spoken a few times.
- **The neighbourhood**: one row per identity with a stable name (kind of device, then brand and id), a one-line summary, how long ago it spoke, how often it usually speaks, and dimming when it has gone quiet.
- **Just heard**: the live tape. Repeated decodes of the same burst and the analyser's companion block for a decode are folded into the identity (see "echoes folded"). Unclaimed bursts and noise are hidden by default; "show bursts" reveals them.
- **What we think it is**: click any row. Guess, why, confidence, cadence, signal, the companion burst, a suggested `-X` flex recipe when rtl_433 offers one (a hint for you; never armed on the live radio), copy raw JSON.
- **The last hour**: who spoke, how many times, and the range a weather station covered. If the tab was in the background for over a minute, a "while you were away" line summarises what arrived.

Categories: weather, TPMS, remote, security, energy, vehicle-key, utility, unknown, unmatched-pulse, noise.

## Cars

Tyre-pressure sensors ride the same 433.92 MHz stream, so a passing car shows up as a "Car tyre" identity with pressure in kPa and psi and temperature in °C (psi/bar/°F from the decoder are converted, mirroring the TPMS sensor scanner). **Wheels usually only speak while the car is moving**; a parked car stays silent, so expect these to be brief and to go stale quickly. Some imported cars use 315 MHz and will not appear here.

Car remotes are labelled *vehicle-key* and marked heard-only. Rolling codes cannot be replayed from this data and the app never transmits.

## Health

`/api/status` (also `/api/health`) reports `raw_lines`, `last_line_age_s`, `ingest_alive`, and a `health` word: `ok`, `quiet` (>45 s without a line from rtl_433), `stalled` (>120 s), `dead`. Ingest-thread deaths are logged and shown under "ingest log" in the header.

## Hardware

Nooelec NESDR SMArt v5, 433 MHz mast, 433.92 MHz, sample rate 1024 kHz, analyser on. Default extra arguments: `-d 0 -g 0 -A -s 1024k -M level -M protocol`. See `docs/HARDWARE.md` and `docs/WORKAROUNDS.md`.
