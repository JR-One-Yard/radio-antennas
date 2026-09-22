# Workarounds

Recorded while building the satellite steal. Later the owner put the telescopic mast on and asked to hunt planes/ships; Over the Fence was then paused on purpose.

## Do not steal a live census by accident

`ism-scan serve` falls back to a demo neighbourhood if the USB claim fails, and it does not reclaim the dongle. A wrapper that called `stop` during install would have dropped a real capture.

**Workaround:** `meteor-lease acquire|pass|release|hunt` is dry-run unless `--commit`. Tests inject `FakeRadio`. The first build session never stopped the live census. The hunt session did, with owner go-ahead.

## Real Meteor pass cannot run unsupervised

AOS needs a QTH, a ≥20° pass in the next few minutes, the telescopic V on the roof, and exclusive USB. None of that was available without taking the live radio.

**Workaround:** `--decoder stub` writes a labelled mock `msu_mr_rgb_MSA_corrected.png` so the product path exists. A real PNG still needs an attended `--decoder satdump --commit` pass.

## QTH unknown

Pass prediction is wrong until lat/lon exist. `qth.json` is gitignored. The autotrack example uses `0,0` on purpose so it cannot be mistaken for a real station.

**Workaround:** `qth.example.json` with nulls. `doctor` reports unset. Did not invent a home coordinate.

## `ism-scan doctor` only sees rtl_433

SatDump holding USB would look like "dongle is free" to Over the Fence's doctor.

**Workaround:** `meteor-lease` also lists `satdump` / `satdump-ui` processes and refuses `--commit` release while they are running.

## SatDump was not installed

Needed for the attended recipe. Installed with `brew install --cask satdump` (1.2.2 → `/Applications/SatDump.app`, `satdump` on PATH). Never launched against the live dongle.

## VIRTUAL_ENV leaked into ism-scan

`meteor-lease doctor` runs `uv run ism-scan` from the 433 folder while itself living in `vhf shift/.venv`. uv warned that VIRTUAL_ENV did not match.

**Workaround:** strip `VIRTUAL_ENV` / `UV_PROJECT*` from the child environment so Over the Fence keeps its own `.venv`.

## Evening vs morning passes

Owner has not said whether evening Meteor passes are worth stealing 433. Spec stays morning-first; the lease does not schedule anything.

## Cron needed a click I cannot do

`crontab -` hung (macOS Full Disk Access / cron permission). Did not wait for a human.

**Workaround:** an attended `scripts/meteor-pass.sh`, not cron. A one-shot calendar agent used for a single pass is not part of this snapshot.

## No ship-name decoder

Homebrew has no AIS-catcher. Did not spend the afternoon compiling it.

**Workaround:** `rtl_power` on 161.9–162.1 MHz (busy or quiet). Plane names come from dump1090. Ship *names* need a later install.

## Garden radio is off until after the space picture

The hunt holds the USB stick. Over the Fence stays paused until the pass hands the dongle back.

## The radio host is separate from the laptop

The NESDR and telescopic live on the radio host. The laptop must not run dump1090 or `ism-scan` against that stick. `meteor-lease` default idle remains `ism-scan` without `host.json` so laptop tests stay 433-shaped. The host copies `host.example.json` → `host.json` with `idle: dump1090` and `bind: tailscale`. SSH as the account that actually exists on that machine.

**Workaround:** acquire/release take a `yard` object. Tests use `FakeYard`. Production uses `LiveYard` (stick.stolen flag + kill dump1090). LaunchAgent `com.oneyard.planes` loops dump1090 but sleeps while stolen, so KeepAlive cannot steal the pass back.

## SatDump brew symlink (5 Sep 2026)

A LaunchAgent on the laptop ran `/opt/homebrew/bin/satdump`; it looked for `/usr/local/share/satdump/satdump_cfg.json` and exited immediately. 433 came back. Retry after peak, SNR 0, no PNG. Empty CADU is not a picture.

**Workaround:** always `/Applications/SatDump.app/Contents/MacOS/satdump`. `find_satdump()` prefers that path even when brew is first on PATH.

## QTH stays off git

Pass prediction is wrong until lat/lon exist in gitignored `qth.json`. Do not commit a station coordinate, and do not schedule a calendar Meteor agent from this tree.

**Workaround:** doctor reports unset. `meteor-pass.sh` is manual. The plane map in `web/planes/index.html` opens at world scale. `scripts/yard-idle.sh` injects the camera from `qth.json` at serve time. Altitude stays at the example **50 m** until you survey it.

## MagicDNS plane map looked like a broken HTTPS site

If another site on the same MagicDNS name has taught the browser HSTS, it rewrites `http://…:10900/` to HTTPS. Port 10900 was plain HTTP, so Chrome showed ERR_SSL_PROTOCOL_ERROR.

**Workaround:** listen on `127.0.0.1:10900` and `tailscale serve --bg --https=10900 http://127.0.0.1:10900` (tailnet only, not Funnel, does not steal `/` on 443). Open `https://the-mini.example.ts.net:10900/` after substituting your host's MagicDNS name.

## Homebrew Python cannot serve Tailscale HTTP

macOS Application Firewall allows `/usr/bin/python3` and Tailscale, not Homebrew Python. Binding `yard_http.py` with Homebrew Python listened on the host's Tailscale IPv4, but the laptop timed out.

**Workaround:** `yard-idle.sh` runs `/usr/bin/python3 scripts/yard_http.py`. Still bind the radio host's Tailscale IPv4 only — not `0.0.0.0`, not Funnel. Leave whatever already owns port 443 alone.

## dump1090 formula name

Homebrew package is `dump1090-fa`; the binary on the radio host may be `dump1090`. Scripts accept either name.

