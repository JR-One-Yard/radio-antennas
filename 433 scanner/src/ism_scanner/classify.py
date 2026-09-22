from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = (
    "weather",
    "tpms",
    "remote",
    "security",
    "energy",
    "vehicle-key",
    "utility",
    "unknown",
    "unmatched-pulse",
    "noise",
)

# Tokens are matched case-insensitively against "<model> <type>" from rtl_433.
# They are drawn from `rtl_433 -R help` (25.12) so the household label covers
# the catalogue rather than the handful of models we have personally heard.

_TPMS = (
    "tpms",
    "schrader",
    "steelmate",
    "tyreguard",
    "eeztire",
    "carchet",
    "tst-507",
    "pmv-107",
    "jansite",
    "elantra",
    "abarth",
    "porsche",
    "solartpms",
    "gm-aftermarket",
    "bmw-gen",
    "hyundai-vdo",
    "renault-0435",
)
_VEHICLE_KEY = (
    "car key",
    "carkey",
    "car-key",
    "car remote",
    "carremote",
    "car-remote",
    "keyless",
    "akhan",
)
_SECURITY = (
    "security",
    "contact",
    "pir",
    "smoke",
    "heat detector",
    "alarm",
    "doorbell",
    "simplisafe",
    "honeywell",
    "dsc",
    "chuango",
    "visonic",
    "kerui",
    "interlogix",
    "yale",
    "risco",
    "cavius",
    "leak",
    "leakage",
    "water detector",
    "motion",
    "x10-security",
    "x10 security",
    "jasco",
    "choice alert",
    "gs 558",
    "gs558",
    "elro",
    "2gig",
    "powercode",
    "chamberlain-cwpirc",
    "wh55",
    "govee-water",
    "govee-h5054",
)
_REMOTE = (
    "remote",
    "switch",
    "keyfob",
    "keeloq",
    "hcs200",
    "hcs300",
    "somfy",
    "gate",
    "garage",
    "shutter",
    "curtain",
    "fan",
    "silvercrest",
    "waveman",
    "intertechno",
    "klikaanklikuit",
    "nexa",
    "proove",
    "megacode",
    "linear",
    "chamberlain",
    "nice flor",
    "nice-flor",
    "markisol",
    "roja flex",
    "rojaflex",
    "cardin",
    "x10-rf",
    "x10 rf",
    "ev1527",
    "sc226",
    "quhwa",
    "blyss",
    "ht680",
    "radiohead",
    "ge color",
    "gecolor",
    "dish",
    "directv",
    "fs20",
    "fht",
    "funkbus",
    "instafunk",
    "smartfire",
    "proflame",
    "regency",
    "srsmith",
    "security+",
    "securityplus",
    "insteon",
    "deltadore",
    "x3d",
    "rosstech",
    "quinetic",
    "lightwaverf",
    "brennenstuhl",
    "mebus",
    "enocean",
    "generic-remote",
    "button",
)
_ENERGY = (
    "energy",
    "power",
    "currentcost",
    "efergy",
    "emontx",
    "solar",
    "revolt",
    "voltcraft",
    "sparsnas",
    "cent-a-meter",
    "blueline",
    "ecodhome",
    "marlec",
    "iboost",
    "geo minim",
    "geo-minim",
    "esic",
    "emt7110",
    "norgo",
    "clipsal",
    "esa1000",
    "esa2000",
    "ec3k",
    "energycount",
    "bm5",
    "battery monitor",
    "elv-em",
    "em1000",
)
_UTILITY = (
    "oil",
    "ultrasonic",
    "tank",
    "liquid level",
    "water meter",
    "flow meter",
    "ert",
    "scm",
    "idm",
    "m-bus",
    "mbus",
    "wmbus",
    "gridstream",
    "landis",
    "badger",
    "orion",
    "neptune",
    "r900",
    "flowis",
    "mueller",
    "hot rod",
    "arad",
    "master meter",
    "dialog3g",
    "apator",
    "watchman",
    "tekelek",
    "thermostat",
    "danfoss",
    "vaillant",
    "calormatic",
    "celsia",
    "watts",
    "cm921",
    "wfht",
    "meter",
)
_WEATHER = (
    "weather",
    "temperature",
    "temp",
    "humidity",
    "thermo",
    "hygro",
    "rain",
    "wind",
    "soil",
    "pool",
    "lightning",
    "uvi",
    "air quality",
    "wh1080",
    "wh3080",
    "wh45",
    "wh46",
    "wh43",
    "wh31",
    "wh32",
    "wh51",
    "wh53",
    "wh65",
    "ws80",
    "ws85",
    "ws90",
    "wn34",
    "acurite",
    "bresser",
    "lacrosse",
    "oregon",
    "fine offset",
    "fineoffset",
    "ecowitt",
    "cotech",
    "ambient",
    "prologue",
    "rubicson",
    "nexus",
    "auriol",
    "govee",
    "inkbird",
    "thermopro",
    "maverick",
    "bbq",
    "grill",
    "meat",
    "moisture",
    "freezer",
    "fridge",
    "alecto",
    "hideki",
    "wt450",
    "wt260",
    "wt405",
    "esperanza",
    "calibeur",
    "globaltronics",
    "gt-wt",
    "gt-tmbbq",
    "tfa",
    "conrad",
    "kedsum",
    "springfield",
    "wg-pb12v1",
    "emos",
    "infactory",
    "ft-004",
    "ft004",
    "philips",
    "wt0124",
    "opus",
    "xt300",
    "ws7000",
    "ws2500",
    "companion",
    "wtr001",
    "eurochron",
    "efth",
    "holman",
    "iweather",
    "ws5029",
    "aok",
    "tbh",
    "ws2032",
    "missil",
    "sharp",
    "spc775",
    "telldus",
    "ft0385",
    "emax",
    "vevor",
    "geevon",
    "baldr",
    "atech",
    "wec-2103",
    "vauno",
    "rainpoint",
    "homelead",
    "arexx",
    "thermor",
    "schou",
    "digitech",
    "solight",
    "kw9010",
    "kw9015",
    "s3318",
    "nc-7104",
    "nc-7345",
    "nc-5849",
    "hyundai-ws",
    "ws senzor",
    "wt-02",
    "wt-03",
    "tx141",
    "tx29",
    "tx35",
    "tx31",
    "tx34",
    "ltv-",
    "ws-2310",
    "ws-3600",
    "f007th",
    "f016th",
    "tx-8300",
    "gasmate",
    "burnhard",
    "amazon basics",
    "oria",
    "sauna",
    "mini-plant",
    "plant",
    "dcf77",
    "ip-th",
    "ip-ha",
    "tsn-70",
    "xc-0324",
    "ft005th",
    "te44",
    "te66",
    "e0107",
    "ttx201",
    "en8822",
    "hg02832",
    "hg05124",
    "afw2a1",
    "aft 77",
    "ahfl",
    "30.3",  # TFA Dostmann family part numbers
)

_TPMS_FIELDS = ("pressure_kPa", "pressure_PSI", "pressure_kpa", "pressure_psi", "pressure_bar")
_WEATHER_FIELDS = (
    "temperature_C",
    "temperature_F",
    "humidity",
    "rain_mm",
    "wind_avg_m_s",
    "wind_max_m_s",
    "wind_dir_deg",
    "uvi",
    "light_lux",
    "moisture",
)
_ENERGY_FIELDS = ("power_W", "energy_kWh", "current_A", "voltage_V")


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    guess: str
    confidence: float
    why: str


def classify(event: dict) -> Classification:
    """Guess what a decoded or pulse event is, with a reason a person can read."""
    if event.get("kind") == "pulse":
        return _classify_pulse(event)

    model = str(event.get("model") or "").strip()
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else event
    typ = str(event.get("type") or (fields.get("type") if isinstance(fields, dict) else "") or "")
    blob = f"{model} {typ}".lower()

    is_tpms_type = typ.strip().upper() == "TPMS"
    if is_tpms_type or _hit(blob, _TPMS) or _has(fields, *_TPMS_FIELDS):
        return Classification(
            "tpms",
            f"Tyre-pressure sensor ({model or 'unknown family'})",
            0.95 if is_tpms_type or "tpms" in blob else 0.85 if _hit(blob, _TPMS) else 0.8,
            "rtl_433 named this TPMS, the model is a tyre-sensor family, or the packet carries "
            "tyre pressure. Wheels usually only speak while the car is rolling.",
        )

    if _hit(blob, _VEHICLE_KEY):
        return Classification(
            "vehicle-key",
            f"Car remote ({model or 'unknown'}) — heard only, rolling codes cannot be replayed",
            0.85,
            "The decoder catalogue lists this as a vehicle key or keyless entry. "
            "This app only listens; it never records enough to clone one.",
        )

    weather_hit = _hit(blob, _WEATHER)
    weather_fields = _has(fields, *_WEATHER_FIELDS)
    if weather_fields and not _hit(blob, _SECURITY + _ENERGY + _UTILITY):
        # A packet carrying temperature/rain/wind is a weather sensor whatever the brand
        # token says (SwitchDoc, Hyundai WS, ...), unless a safety/energy family claims it.
        return Classification(
            "weather",
            f"Weather or garden sensor ({model or 'temperature/humidity packet'})",
            0.93 if weather_hit else 0.75,
            "Temperature, humidity, rain, or wind fields, or a weather-station model name.",
        )

    if _hit(blob, _SECURITY):
        return Classification(
            "security",
            f"Alarm, contact, motion, smoke, leak, or doorbell ({model or 'unknown'})",
            0.86,
            "The model or type matches security, safety, and doorbell families.",
        )

    if _hit(blob, _ENERGY) or _has(fields, *_ENERGY_FIELDS):
        return Classification(
            "energy",
            f"Power or energy monitor ({model or 'unknown'})",
            0.86 if _hit(blob, _ENERGY) else 0.7,
            "The model matches an electricity-monitor family, or the packet carries power.",
        )

    if _hit(blob, _UTILITY) and not _hit(blob, ("weather", "thermo", "hygro")):
        return Classification(
            "utility",
            f"Tank, meter, thermostat, or utility sensor ({model or 'unknown'})",
            0.78,
            "The model matches oil-tank, water/power-meter, heating, or similar utility gear.",
        )

    if _hit(blob, _REMOTE):
        return Classification(
            "remote",
            f"Button, gate, switch, or shutter remote ({model or 'unknown'})",
            0.84,
            "The model matches a remote-control or switch family.",
        )

    if weather_hit:
        return Classification(
            "weather",
            f"Weather or garden sensor ({model or 'temperature/humidity packet'})",
            0.82,
            "A weather-station model name, though this packet carries no readings.",
        )

    if _looks_like_button(fields):
        return Classification(
            "remote",
            f"Likely a button or remote ({model or 'unlabelled'})",
            0.55,
            "Packet has command/button/channel fields but no weather or TPMS payload.",
        )

    if model:
        return Classification(
            "unknown",
            f"Decoded as {model}, but the catalogue does not map it to a household job",
            0.4,
            "rtl_433 recognised a model; this app has no stronger household label yet.",
        )

    return Classification(
        "unknown",
        "Decoded radio packet with no model name",
        0.2,
        "JSON arrived without a model we can hang a guess on.",
    )


MIN_PLAUSIBLE_PULSE_US = 50  # real 433 MHz ISM devices key at ~100 µs or slower


def is_noise_pulse(event: dict) -> bool:
    """Single spikes, two-or-three pulse blips, and sub-50 µs "PWM" are the noise floor."""
    modulation = str(event.get("modulation") or "")
    count = event.get("pulse_count")
    if "Single pulse" in modulation or "just noise" in modulation:
        return True
    if isinstance(count, int | float) and count <= 3:
        return True
    hint = event.get("flex_hint")
    if isinstance(hint, dict):
        short = hint.get("s")
        if isinstance(short, int | float) and 0 < short < MIN_PLAUSIBLE_PULSE_US:
            return True
    return False


def _classify_pulse(event: dict) -> Classification:
    modulation = str(event.get("modulation") or "").strip() or "unrecognised envelope"
    kind = str(event.get("rf_kind") or "burst")
    demod_ok = bool(event.get("demod_attempted") and not event.get("demod_failed"))
    if is_noise_pulse(event):
        return Classification(
            "noise",
            f"Noise floor — a {kind} blip too short to carry data",
            0.1,
            "A single spike or a two-or-three pulse blip. rtl_433 itself says "
            "'probably just noise'. Grouped so the tape stays readable.",
        )
    if "No clue" in modulation:
        return Classification(
            "unmatched-pulse",
            f"Unrecognised {kind} chatter — timing matches no known 433 MHz recipe",
            0.2,
            "The pulse analyser heard energy but could not name a modulation. "
            "Often the tail of a real packet or broadband interference.",
        )
    if event.get("flex"):
        guess = f"Unclaimed {kind} burst, possibly {modulation}"
        confidence = 0.55
        why = (
            "No catalogue decoder claimed it. rtl_433 suggested a flex recipe from the pulse "
            "timings; it is shown as a hint only and is never armed on the live radio."
        )
    elif demod_ok:
        guess = f"{kind} burst using {modulation} (a decoder may have claimed it separately)"
        confidence = 0.5
        why = "Pulse analysis guessed a modulation and attempted demodulation."
    else:
        guess = f"Unclaimed {kind} burst using {modulation}"
        confidence = 0.45
        why = "Pulse analysis named a modulation, but no device decoder accepted the packet."
    return Classification("unmatched-pulse", guess, confidence, why)


def _hit(blob: str, tokens: tuple[str, ...]) -> bool:
    return any(token in blob for token in tokens)


def _has(fields: object, *names: str) -> bool:
    if not isinstance(fields, dict):
        return False
    return any(name in fields and fields[name] not in (None, "") for name in names)


def _looks_like_button(fields: object) -> bool:
    if not isinstance(fields, dict):
        return False
    keys = {str(key).lower() for key in fields}
    return bool(keys & {"button", "cmd", "command", "keycode", "dip", "tristate"})
