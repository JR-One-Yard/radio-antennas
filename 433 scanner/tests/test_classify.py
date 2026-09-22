from ism_scanner.classify import classify
from ism_scanner.normalize import sighting_from_decoded


def _event(**fields):
    return sighting_from_decoded(fields)


def test_weather_station_from_live_cotech():
    sighting = _event(
        model="Cotech-367959",
        id=53,
        temperature_F=62.8,
        humidity=78,
        rain_mm=318.6,
        protocol=153,
    )
    assert sighting["category"] == "weather"
    assert sighting["confidence"] >= 0.9
    assert "53" in sighting["entity_key"]


def test_tpms_beats_car_brand():
    sighting = _event(model="Toyota", type="TPMS", id="A1B2C3D4", pressure_kPa=220)
    assert sighting["category"] == "tpms"
    assert "Tyre" in sighting["guess"]


def test_live_hyundai_vdo_is_tpms_with_car_name():
    sighting = _event(
        model="Hyundai-VDO", type="TPMS", id="0badf00d", pressure_kPa=251.6, temperature_C=21.0
    )
    assert sighting["category"] == "tpms"
    assert sighting["confidence"] >= 0.9
    assert sighting["name"] == "Car tyre · Hyundai VDO 0badf00d"
    assert "252 kPa" in sighting["summary"]
    assert "36.5 psi" in sighting["summary"]


def test_tpms_family_without_type_field():
    sighting = _event(model="Schrader-EG53MA4", id="abc", flags=1)
    assert sighting["category"] == "tpms"


def test_car_remote_is_vehicle_key_and_says_receive_only():
    sighting = _event(model="Ford-CarRemote", id="1234", button=2)
    assert sighting["category"] == "vehicle-key"
    assert "cannot be replayed" in sighting["guess"]


def test_leak_detector_is_security_not_weather():
    sighting = _event(model="Govee-Water", id="9", event="Leak")
    assert sighting["category"] == "security"


def test_utility_meter_and_thermometer_do_not_collide():
    assert _event(model="ERT-SCM", id="1", consumption=1234)["category"] == "utility"
    assert _event(model="Rubicson-Thermometer", id="1", temperature_C=20)["category"] == "weather"


def test_switchdoc_style_brand_with_readings_is_weather():
    sighting = _event(model="SwitchDoc-Labs", id="1", temperature_C=20.5, humidity=60)
    assert sighting["category"] == "weather"


def test_remote_from_command_field():
    sighting = _event(model="Mystery-TX", cmd="ON", channel=4)
    assert sighting["category"] == "remote"


def test_unknown_model_stays_visible():
    sighting = _event(model="BrandX-9000", id="zz")
    assert sighting["category"] == "unknown"
    assert "BrandX-9000" in sighting["guess"]


def test_pulse_no_clue_is_low_confidence():
    labelled = classify(
        {"kind": "pulse", "modulation": "No clue...", "rf_kind": "FSK", "pulse_count": 26}
    )
    assert labelled.category == "unmatched-pulse"
    assert labelled.confidence <= 0.2


def test_single_pulse_is_noise():
    labelled = classify(
        {
            "kind": "pulse",
            "modulation": "Single pulse detected. Probably Frequency Shift Keying or just noise...",
            "rf_kind": "OOK",
            "pulse_count": 1,
        }
    )
    assert labelled.category == "noise"
    assert labelled.confidence <= 0.1


def test_sub_50us_pwm_is_noise():
    from ism_scanner.normalize import sighting_from_pulse

    sighting = sighting_from_pulse(
        {
            "kind": "pulse",
            "rf_kind": "OOK",
            "pulse_count": 11,
            "modulation": "Pulse Width Modulation with sync/delimiter",
            "flex": "n=name,m=OOK_PWM,s=11,l=111,r=37,g=0,t=0,y=174",
        }
    )
    assert sighting["category"] == "noise"
    assert sighting["entity_key"] == "noise"


def test_flex_hint_is_a_suggestion_only():
    labelled = classify(
        {
            "kind": "pulse",
            "modulation": "Pulse Width Modulation with sync/delimiter",
            "rf_kind": "OOK",
            "pulse_count": 40,
            "flex": "n=name,m=OOK_PWM,s=300,l=900,r=9000",
        }
    )
    assert labelled.category == "unmatched-pulse"
    assert "never armed" in labelled.why
