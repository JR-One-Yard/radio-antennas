# Workarounds and remaining physical verification

## Workarounds used to complete the project

### No SDR or known TPMS sensor was available

The built-in simulator emits deterministic Toyota- and Schrader-shaped events, updates, unrelated
433 MHz traffic, and malformed JSON. The example capture drives the same replay path. This proves
normalization, filtering, state, staleness, rendering, and diagnostics without claiming RF
reception was physically tested.

### `rtl_433` was not installed on the development Mac

Tests create a temporary executable that behaves like `rtl_433`: it receives `-f` and `-F json`,
emits TPMS JSON, can fail with a non-zero status and stderr, and can remain alive until the scanner
terminates it. This verifies the real subprocess boundary and cleanup. `doctor` reports the missing
production binary honestly.

### The target vehicle, sensor family, and market frequency were unspecified

The live default is the common Australian 433.92 MHz frequency, while `--frequency` and repeatable
`--rtl-arg` options leave 315 MHz, non-default sample rates, and explicit decoder selection open.
The normalizer accepts common `rtl_433` field aliases rather than assuming one manufacturer.

### Account checkout details stayed private

Public listings were compared using item price plus stated postage. The hardware guide records a
timestamp and distinguishes verified offers from unsubstantiated related-product prices. A later
live buy-box check showed the NESDR SMArt v5 bundle in stock for AU$86.95, sold by Nooelec
Australia and fulfilled by Amazon. That bundle is the receiver these tools share. Account-specific
payment and delivery details are not recorded here.

### The parent folder was already an empty Git repository

No nested `.git` directory was created. `TPMS sensor scanner/` contains its own `pyproject.toml`,
licence, ignore rules, source, tests, and docs, so it is independently repo-ready while remaining
trackable by the existing parent repository.

## Physical verification still required

The NESDR SMArt v5 is the shared receiver. Still worth doing on a wheel you own:

1. Install `rtl_433` and run `uv run tpms-scan doctor`.
2. Confirm the USB receiver is visible and can receive a known signal.
3. Scan at the vehicle's documented frequency after waking the sensors.
4. Compare one decoded pressure with a calibrated gauge; do not treat radio telemetry as a safety
   measurement until this check is complete.
5. Replay a private capture through the scanner and add a redacted regression fixture if the
   decoder uses fields not represented by the bundled examples.

## Decisions intentionally left to the owner

- Which owned vehicle/sensor family and market frequency to validate first.
- Whether future versions should persist history, publish MQTT, or add a dashboard.
- Whether this subfolder should later be extracted into its own remote Git repository.
