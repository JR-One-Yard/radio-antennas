# Workarounds

Recorded while finishing Over the Fence without stopping for decisions.

## Pipe buffering hid live packets

`rtl_433` block-buffers JSON when stdout is a pipe, so a quiet neighbourhood never filled the buffer. Live serve now attaches a PTY to stdout so each packet flushes immediately. If `pty.openpty()` fails, it falls back to pipes.

`rtl_433 -F json -A` writes decoded devices to stdout and pulse analysis to stderr. The ingest path reads both. Capture files prefix analyser lines with `stderr:` so replay can reconstruct that split.

## `[R82XX] PLL not locked!`

Seen on a successful 12-second listen that still decoded a weather station. Treated as a noisy tuner message, not a fatal error.

## Every burst arrives three times

Each weather packet can produce **two identical JSON decodes** in the same second (same fields, same RSSI to three decimals) and then **one analyser block** for the same burst (same RSSI to 0.1 dB; alternately "Manchester coding, 108 pulses" and "PWM with multiple packets, 215 pulses"). Left alone, one weather reading was three tape rows and two identities.

`ism_scanner/dedup.py` folds these in the ingest thread:

- a decode with the same identity, same payload, and a timestamp within 1 s of the previous one is a **repeat** (`duplicate_of`); the entity's `repeats` counter goes up, nothing new is drawn;
- a pulse whose RSSI is within 0.6 dB and timestamp within 1 s of a recent decode is a **companion** (`companion_of`); it is attached to that decode's entity as `companion` and not shown as an unclaimed burst.

rtl_433 emits the decode before the analyser text, but the two come from different file descriptors, so live serve **holds an unclaimed pulse for 250 ms** before publishing it, in case its decode is still in flight. Replay and `simulate` use a zero hold so output order is stable.

`-M time:iso:usec:utc` is now passed so both streams carry microseconds. The analyser's `Detected OOK package <time>` line honours the same format.

## Noise minted a new identity per burst

Pulse identity used to include the exact pulse count, so a broadband splat that rtl_433 split into forty "No clue" packages became forty identities. Identity is now by *shape*:

- single spikes and ≤3-pulse blips → one identity, `noise`, category **noise**, confidence 0.1 (rtl_433 itself says "probably just noise");
- "No clue" → one identity per RF kind (`pulse:ook:no-clue`), confidence 0.2;
- bursts with a flex hint → grouped by modulation scheme and a ~25 % geometric bucket of the short-pulse width, so 493 µs and 495 µs land together.

The UI hides `unmatched-pulse` and `noise` by default behind a "show bursts" toggle with a count badge.

## Flex hints are suggestions

`Use a flex decoder with -X '...'` lines are parsed and shown in the inspector with a copy button, labelled as a hint. They are **never** added to the live `rtl_433` command. Arming an unverified flex decoder on live RF would print garbage decodes with real-looking IDs.

## `pkill -f "ism-scan serve"` kills the shell that typed it

The shell's own command line contains that string, so `pkill -f` matches the shell first and the server survives. `ism-scan stop` finds real launchers (`python … ism-scan serve`, `uv run ism-scan serve`) by pid, skips shells/greps/its own ancestry, and SIGTERMs them. `ism-scan doctor` lists who currently holds the radio.

Only one process may open the dongle. If another `rtl_433` is running when `serve` starts, the status message names its pid; the fallback-to-simulator message includes it too.

## Health from `raw_lines`

`raw_lines` in `/api/status` counts every line read from `rtl_433`. `last_line_age_s` and `health` derive from it: `ok`, `quiet` (>45 s silent — unusual with `-A` on live RF), `stalled` (>120 s), `dead` (ingest thread gone or errored). Ingest-thread deaths are logged into `status.log`, which the UI shows under "ingest log".

## Disabled-by-default protocols

rtl_433 ships many decoders off (`*` in `-R help`). This version uses the default enabled set plus the pulse analyser, rather than enabling every disabled protocol (some are 868 MHz / North American meters). Owner decision.

## Live-to-simulate fallback

`ism-scan serve` tries the USB radio first. If `rtl_433` cannot start, it serves a paced simulator so the UI can still be demonstrated. Use `--live-only` to refuse that fallback.

## No persistence by default

Sightings live in process memory (latest identity, a 400-event tape, an hour of hearing timestamps for the digest, up to 180 trend points per decoded identity). Restarting forgets the neighbourhood. `--capture PATH` appends the *raw* rtl_433 lines to a JSONL file (replayable with `ism-scan replay`); `captures/` is gitignored. That file will contain neighbours' TPMS ids — keep it local.

## Parent git repository

No nested `.git` was created. This folder is repo-ready via its own `pyproject.toml` while remaining inside Hardware and Telemetry.

## Decisions not taken

- Whether to persist history (SQLite) or publish MQTT / Home Assistant.
- Whether to enable extra disabled decoders (`-R`), and which.
- Whether 315 MHz imported-car TPMS should be a second listen (needs a second dongle or time-slicing; both lose 433 coverage while away).
