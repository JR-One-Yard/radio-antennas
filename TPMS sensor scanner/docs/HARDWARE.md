# Hardware and live setup

Research checked: 2 September 2026. Purchase status updated: 3 September 2026.
Prices, exchange rates, stock, postage, and Prime eligibility change.

## Receiver in use

[Nooelec NESDR SMArt v5 Bundle on Amazon Australia](https://www.amazon.com.au/gp/product/B01GDN1T4S?smid=ALY61F53Y7KL8&psc=1)

- This is the shared stick for the tools in this repository.
- The pre-purchase check showed **AU$86.95**, in stock, sold by Nooelec Australia, and fulfilled
  by Amazon. Account checkout and delivery details stay private.
- This is Nooelec SKU 100700: an RTL2832U receiver with the current R820T2/R860 tuner, 0.5 ppm
  TCXO, aluminium enclosure, integrated heatsink, and female SMA input.
- The bundle includes a magnetic antenna base with 2 m RG58 cable, a fixed 433 MHz ISM mast, a
  fixed UHF mast, and a variable telescopic mast. No separate antenna, amplifier, filter, bias tee,
  or adapter is needed for the first TPMS test.
- Live 433.92 MHz reception works on this stick. A calibrated tyre-gauge comparison is still not
  done. Follow [First live check](#first-live-check) on a wheel you are allowed to test.

## Cheapest complete options found

### 1. Cheapest credible delivered kit — non-Amazon

[Nooelec TV28T v2 / NESDR Mini on eBay Australia](https://www.ebay.com.au/itm/272269950902)

- **AU$28.99 delivered**: AU$28.99 item price with free SpeedPAK postage to Australia.
- Listing showed three available and 44 sold when checked.
- Genuine older RTL2832U/R820T receiver with an included MCX starter antenna; it covers 433.92 MHz
  and works with `rtl_433`.
- The older R820T is less frequency-stable than modern TCXO models, but remains functional for
  close-range TPMS reception. Extend the telescopic antenna to roughly 16.5–17.3 cm.

### 2. Purchased Amazon option

[Nooelec NESDR SMArt v5 Bundle on Amazon Australia](https://www.amazon.com.au/gp/product/B01GDN1T4S?smid=ALY61F53Y7KL8&psc=1)

- Purchased on 3 September 2026 after a live buy-box check showed AU$86.95, in stock, sold by
  Nooelec Australia, and shipped by Amazon.
- It was selected over the AU$75.95 Mini 2+ because the AU$11 premium adds native SMA, a shielded
  metal enclosure, better thermal management, the newer low-noise SMArt v5 design, and a dedicated
  433 MHz antenna.
- It was selected over the same-price SMArTee v2 bundle because the older model's always-on bias
  tee is unnecessary for a passive TPMS antenna.
- Prime membership and checkout details are account-specific; the completed Amazon order is the
  source of truth for the final delivery promise.

### Next-best trusted fallback

[Official RTL-SDR Blog V3 kit on eBay Australia](https://www.ebay.com.au/itm/283144516411)

- Listed at US$43.95 / approximately **AU$62.58 delivered**, with free Economy International
  Shipping from Shanghai.
- Includes the genuine RTL2832U/R820T2 receiver, TCXO, SMA dipole antenna kit, mounts, and cable.
- Seller must be `rtl-sdr-blog`, the manufacturer's documented official eBay identity.

For a newer but unverified generic option, the
[RTL2832U/R820T2/1 ppm TCXO dongle](https://www.ebay.com.au/itm/363208084508) is AU$53.58
delivered. Adding [two Sydney-stocked 433 MHz SMA antennas](https://www.ebay.com.au/itm/154099719354)
brings the functional total to **AU$71.48**. Confirm that it has standard SMA female and use
`rtl_test`; the seller is not an authorised RTL-SDR Blog reseller.

The new [V4L dongle](https://www.rtl-sdr.com/product/rtl-sdr-blog-v4l-lite-r828s-rtl2832u-1ppm-tcxo-sma-software-defined-radio-dongle-only/)
is US$37.95 but is not the cheapest *functional kit*: it has no antenna and requires newer
R828S-capable drivers. The matching antenna is another US$17.95.

## Minimum hardware specification

- RTL2832U USB demodulator.
- R820T, R820T2/R860, R828D, or supported R828S tuner; all cover 433.92 MHz.
- An antenna connected to the dongle. For a dipole, start near 17.3 cm per side at 433.92 MHz and
  adjust placement before buying amplifiers or filters.
- USB-A port or a data-capable USB adapter for the host computer.

Avoid fixed 433 MHz ASK receiver modules sold for Arduino. They are cheap, but they cannot provide
the wideband I/Q samples expected by `rtl_433` and do not cover the mix of ASK/OOK and FSK TPMS
protocols.

## Install the decoder

### macOS

```sh
brew install rtl_433
rtl_433 -V
```

### Debian or Ubuntu

```sh
sudo apt update
sudo apt install rtl-433
rtl_433 -V
```

### Windows

Use a current binary from the
[`rtl_433` releases](https://github.com/merbanan/rtl_433/releases). An RTL2832U receiver may need
its interface changed to WinUSB with Zadig. Keep the extracted executable and DLLs together, then
pass the executable path:

```powershell
uv run tpms-scan scan --rtl-433 C:\tools\rtl_433\rtl_433.exe
```

## First live check

1. Connect the antenna before the receiver.
2. Put it within a few metres of a wheel you own or are authorized to test.
3. Run `uv run tpms-scan doctor`.
4. Drive briefly or follow the vehicle service procedure to wake its sensors.
5. Run `uv run tpms-scan scan --frequency 433.92M --verbose-rejections`.
6. If the vehicle is from a 315 MHz market, retry with `--frequency 315M`.

Australia commonly uses 433.92 MHz, but frequency follows the sensor/vehicle market, not the
scanner's location. `rtl_433` supports many Toyota, Ford, Schrader, Renault, Citroën, Hyundai,
BMW/Audi, Nissan, aftermarket, and other TPMS families, but not every sensor.

## Capturing a reproducible report

Keep raw files private because they contain sensor IDs:

```sh
mkdir -p captures
rtl_433 -f 433.92M -F json > captures/my-vehicle.jsonl
uv run tpms-scan replay captures/my-vehicle.jsonl
```

For an undecoded signal, follow the upstream
[`rtl_433` analysis guidance](https://triq.org/rtl_433/ANALYZE.html). Redact identifiers before
sharing decoded captures. Raw I/Q recordings can be large and can include unrelated nearby radio
traffic.

## Sources

- [`rtl_433` supported protocols and platform support](https://github.com/merbanan/rtl_433)
- [Official RTL-SDR seller identities and counterfeit warning](https://www.rtl-sdr.com/genuine/)
- [Homebrew `rtl_433` package](https://formulae.brew.sh/formula/rtl_433)
- [ACMA technical standards](https://www.acma.gov.au/technical-standards)
