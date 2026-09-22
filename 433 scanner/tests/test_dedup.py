from ism_scanner.dedup import Deduper
from ism_scanner.normalize import PulseAssembler, interpret_line, sighting_from_decoded

COTECH = {
    "time": "2026-09-04T11:36:19.104211",
    "model": "Cotech-367959",
    "id": 53,
    "temperature_F": 61.7,
    "humidity": 81,
    "rssi": -11.11,
    "snr": 12.226,
}
COMPANION_BLOCK = [
    "Detected OOK package 2026-09-04T11:36:19.104211",
    "Analyzing pulses...",
    "Total count:  219,  width: 253.90 ms",
    "RSSI: -11.1 dB SNR: 12.2 dB Noise: -23.3 dB",
    "Guessing modulation: Pulse Width Modulation with multiple packets",
    "Attempting demodulation... short_width: 493, long_width: 975",
    "Use a flex decoder with -X 'n=name,m=OOK_PWM,s=493,l=975,r=5883,g=1034,t=193,y=0'",
]
NOISE_BLOCK = [
    "Detected OOK package 2026-09-04T11:36:04.000000",
    "Analyzing pulses...",
    "Total count:    1,  width: 0.01 ms",
    "RSSI: -12.0 dB SNR: 10.8 dB Noise: -22.8 dB",
    "Guessing modulation: Single pulse detected. Probably Frequency Shift Keying or just noise...",
    "view at https://triq.org/pdv/#AAB1",
]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _pulse(lines):
    assembler = PulseAssembler()
    out = []
    for line in lines:
        out.extend(interpret_line(line, assembler, from_stderr=True))
    leftover = assembler.flush()
    if leftover:
        out.append(leftover)
    assert len(out) == 1
    return out[0]


def test_identical_second_decode_is_a_repeat():
    clock = Clock()
    deduper = Deduper(clock=clock)
    first = sighting_from_decoded(dict(COTECH))
    second = sighting_from_decoded(dict(COTECH))
    assert deduper.push(first) == [first]
    clock.now += 0.01
    out = deduper.push(second)
    assert out == [second]
    assert second["duplicate_of"] == first["entity_key"]
    assert deduper.repeats == 1


def test_changed_reading_is_not_a_repeat():
    deduper = Deduper(clock=Clock())
    first = sighting_from_decoded(dict(COTECH))
    later = sighting_from_decoded({**COTECH, "humidity": 82})
    deduper.push(first)
    deduper.push(later)
    assert "duplicate_of" not in later


def test_companion_pulse_after_decode_is_claimed():
    clock = Clock()
    deduper = Deduper(clock=clock)
    decode = sighting_from_decoded(dict(COTECH))
    deduper.push(decode)
    clock.now += 0.05
    pulse = _pulse(COMPANION_BLOCK)
    out = deduper.push(pulse)
    assert out == [pulse]
    assert pulse["companion_of"] == decode["entity_key"]
    assert decode["companion"]["pulse_count"] == 219
    assert deduper.companions == 1


def test_companion_pulse_before_decode_is_held_then_claimed():
    clock = Clock()
    deduper = Deduper(hold_seconds=0.3, clock=clock)
    pulse = _pulse(COMPANION_BLOCK)
    assert deduper.push(pulse) == []  # held
    clock.now += 0.1
    decode = sighting_from_decoded(dict(COTECH))
    out = deduper.push(decode)
    assert out[0] is decode
    assert out[1] is pulse
    assert pulse["companion_of"] == decode["entity_key"]


def test_unclaimed_pulse_is_released_after_hold():
    clock = Clock()
    deduper = Deduper(hold_seconds=0.3, clock=clock)
    pulse = _pulse(NOISE_BLOCK)
    assert deduper.push(pulse) == []
    clock.now += 0.2
    assert deduper.tick() == []
    clock.now += 0.2
    assert deduper.tick() == [pulse]
    assert "companion_of" not in pulse


def test_far_rssi_is_not_a_companion():
    clock = Clock()
    deduper = Deduper(hold_seconds=0.0, clock=clock)
    decode = sighting_from_decoded({**COTECH, "rssi": -3.0})
    deduper.push(decode)
    pulse = _pulse(COMPANION_BLOCK)
    assert deduper.push(pulse) == [pulse]
    assert "companion_of" not in pulse


def test_flush_returns_held_pulses():
    deduper = Deduper(hold_seconds=5.0, clock=Clock())
    pulse = _pulse(NOISE_BLOCK)
    deduper.push(pulse)
    assert deduper.flush() == [pulse]
    assert deduper.flush() == []
