# TPMS sensor scanner

A receive-only command-line tool that turns [`rtl_433`](https://github.com/merbanan/rtl_433)
JSON into normalized tyre-pressure sensor telemetry. It works with capture files and a built-in
simulator before you buy an SDR.

> This is an experimental telemetry tool, not a calibrated tyre gauge or safety system. Receive
> only signals you are authorized to inspect, keep sensor identifiers private, and confirm tyre
> pressure with approved equipment.

## Project status

The software, simulator, replay path, tests, and live `rtl_433` integration are complete. The
receiver is the same Nooelec NESDR SMArt v5 shared with the other tools in this repository.
Comparison with a calibrated tyre gauge is still not part of this tool; see the
[hardware guide](docs/HARDWARE.md).

## Quick start without hardware

Requirements: Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
uv run tpms-scan simulate
uv run tpms-scan simulate --format json
uv run tpms-scan replay examples/tpms-sample.jsonl
uv run pytest
```

The simulator deliberately includes unrelated radio traffic and malformed input. These are counted
and skipped to prove that a long-running scan survives noisy input.

## Live scanning

You need:

1. A receive-capable RTL-SDR with an RTL2832U demodulator and a tuner covering 433.92 MHz.
2. An antenna; the short antenna included with most bundles is enough for close-range testing.
3. `rtl_433` installed and visible on `PATH`.

On macOS:

```sh
brew install rtl_433
uv run tpms-scan doctor
uv run tpms-scan scan
```

The Australian default is 433.92 MHz. Verify the frequency for the vehicle and market:

```sh
uv run tpms-scan scan --frequency 315M
uv run tpms-scan scan --model Toyota --sensor-id A1B2C3D4
uv run tpms-scan scan --format json > authorized-tpms-observations.jsonl
```

Some decoders need a non-default sample rate or explicit protocol setting. Pass an individual
`rtl_433` argument with `--rtl-arg`; use the equals form when its value begins with `-`:

```sh
uv run tpms-scan scan --rtl-arg=-R --rtl-arg=88 --rtl-arg=-s --rtl-arg=1024k
```

Run `uv run tpms-scan scan --help` for filtering, staleness, output, and process options.

## Commands

- `simulate`: deterministic Toyota and Schrader-style events; no hardware or `rtl_433` required.
- `replay PATH`: process an `rtl_433 -F json` JSONL capture; use `-` to read standard input.
- `scan`: own an `rtl_433` subprocess and stream observations from a real receiver.
- `doctor`: check Python and `rtl_433`; hardware is verified only by a live scan.

JSON mode writes only versioned normalized records to standard output. Rejection counters,
warnings, and summaries go to standard error, so piping remains safe.

## Expected live behavior

Direct TPMS transmitters conserve battery. A parked vehicle may remain silent; a short drive,
wheel rotation, or a manufacturer service activation tool may be required. The scanner cannot
reliably infer wheel position from one receiver.

If no sensor appears:

1. Put the antenna within a few metres of a known, recently active wheel.
2. Confirm the receiver with `rtl_test` or another known 433 MHz source.
3. Run `rtl_433 -F json -M level -f 433.92M` directly and inspect its diagnostics.
4. Check the vehicle's market frequency and the
   [supported decoder list](https://github.com/merbanan/rtl_433#supported-device-protocols).
5. Follow `rtl_433`'s signal-analysis guidance before assuming the scanner is faulty.

See [hardware and installation details](docs/HARDWARE.md), the
[implementation plan](docs/plans/2026-09-02-001-feat-tpms-sensor-scanner-plan.md), and
[recorded workarounds](docs/WORKAROUNDS.md).

## Development

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The package has no runtime Python dependencies. Tests cover normalization, state and staleness,
all input modes, malformed traffic, process failure, early process termination, CLI filtering,
and stdout/stderr separation.

## Privacy and licence

TPMS transmissions can expose persistent sensor IDs belonging to nearby vehicles. Captures and raw
IQ files are ignored by default; redact IDs before sharing fixtures or bug reports.

The scanner is MIT licensed. `rtl_433` is a separate GPL-2.0-or-later program invoked through its
command-line interface and is not redistributed here.
