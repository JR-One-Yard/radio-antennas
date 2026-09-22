# Hardware — VHF satellite steal

- Receiver: Nooelec NESDR SMArt v5. Set the USB serial from `rtl_test` into `host.json`. One stick.
- Radio host: the machine that holds the dongle. Copy `host.example.json` to `host.json`. Bind `127.0.0.1` or `tailscale`, never `0.0.0.0`.
- Mast now: bundled telescopic, **shallow V ~120°**, each arm **~54.5 cm**, roughly N–S (airband / Meteor 137.9 MHz). Idle = dump1090.
- Mast later (interchangeable, minutes): long black fixed whip (~27 cm) 433 MHz. Idle = Over the Fence. No second dongle.
- No bias-T on the SMArt v5. No masthead LNA unless you power it separately.
- One USB owner. dump1090, rtl_433, rtl_fm, and SatDump cannot share the dongle.
- Decoder: SatDump 1.2.2 **app binary** `/Applications/SatDump.app/Contents/MacOS/satdump`. Pipeline `meteor_m2-x_lrpt`, bias off.
- Prefer Meteor-M N2-4 (NORAD 59051). N2-3 (57166) is the spare; its LRPT antenna is tilted.
- Plane map HTTP binds the radio host, port 10900. Not `0.0.0.0`.
- `qth.json` is the station, gitignored. The committed map opens at world scale. `scripts/yard-idle.sh` injects the camera from `qth.json` at serve time. Altitude defaults to 50 m unless surveyed.
