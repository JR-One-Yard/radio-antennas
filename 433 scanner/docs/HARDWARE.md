# Hardware notes

- Receiver: Nooelec NESDR SMArt v5. Read the USB serial with `rtl_test` if you need to pin a device.
- Mast: long black fixed whip (~10.5 in / 27 cm), 433 MHz. Not the telescopic, not the short UHF stub.
- Frequency: 433.92 MHz (Australian ISM / TPMS). Tyre sensors usually transmit only while the wheel is rolling.
- Analyser RSSI alone does not separate a real packet from noise. Pulse shape does (see `docs/WORKAROUNDS.md`).
- Only one process may open the dongle. `uv run ism-scan doctor` shows who holds it; `uv run ism-scan stop` releases it.
