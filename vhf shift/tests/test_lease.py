from pathlib import Path

from meteor_lease.idle import FakeYard
from meteor_lease.lease import acquire, release, stub_pass
from meteor_lease.png import write_mock_strip
from meteor_lease.radio import FakeRadio, listening_ok


def test_dry_run_acquire_does_not_stop():
    radio = FakeRadio(dongle_free=False, serve_running=True)
    yard = FakeYard()
    acquire(radio, commit=False, yes=True, prompt=lambda _m: None, yard=yard)
    assert radio.stops == 0
    assert radio.serve_running is True
    assert yard.steals == 0


def test_commit_acquire_stops_and_frees():
    radio = FakeRadio(dongle_free=False, serve_running=True)
    yard = FakeYard()
    after = acquire(radio, commit=True, yes=True, prompt=lambda _m: None, yard=yard)
    assert radio.stops == 1
    assert yard.steals == 1
    assert after.dongle_free is True
    assert radio.serve_running is False


def test_commit_release_starts_live_only():
    radio = FakeRadio(dongle_free=True, serve_running=False, live=None)
    yard = FakeYard(idle="ism-scan")
    after = release(radio, commit=True, yes=True, prompt=lambda _m: None, yard=yard)
    assert radio.serves == 1
    assert listening_ok(after.live)


def test_dump1090_release_does_not_start_ism_scan():
    radio = FakeRadio(dongle_free=True, serve_running=False, live=None)
    yard = FakeYard(idle="dump1090")
    release(radio, commit=True, yes=True, prompt=lambda _m: None, yard=yard)
    assert radio.serves == 0
    assert yard.givebacks == 1
    assert yard.dump1090 is True


def test_dump1090_acquire_steals_without_433_start():
    radio = FakeRadio(dongle_free=False, serve_running=False)
    yard = FakeYard(idle="dump1090", dump1090=True)
    acquire(radio, commit=True, yes=True, prompt=lambda _m: None, yard=yard)
    assert yard.steals == 1
    assert yard.dump1090 is False
    assert radio.serves == 0


def test_release_refuses_if_satdump_still_up():
    radio = FakeRadio(satdump_running=True)
    yard = FakeYard()
    try:
        release(radio, commit=True, yes=True, prompt=lambda _m: None, yard=yard)
    except Exception as error:
        assert "SatDump still holds" in str(error)
    else:
        raise AssertionError("expected LeaseError")
    assert radio.serves == 0
    assert yard.givebacks == 0


def test_listening_ok_rejects_simulator():
    assert not listening_ok(
        {
            "state": "simulating",
            "source": "simulate",
            "workaround": "live-to-simulate-fallback",
        }
    )
    assert listening_ok({"state": "listening", "source": "rtl_433", "workaround": None})


def test_stub_pass_writes_png(tmp_path: Path):
    png = stub_pass(tmp_path)
    assert png.is_file()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.name == "msu_mr_rgb_MSA_corrected.png"


def test_uv_env_drops_virtual_env(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/wrong")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/tmp/wrong")
    from meteor_lease.radio import _uv_env

    env = _uv_env()
    assert "VIRTUAL_ENV" not in env
    assert "UV_PROJECT_ENVIRONMENT" not in env


def test_mock_strip_is_png(tmp_path: Path):
    path = write_mock_strip(tmp_path / "strip.png")
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert data.endswith(b"IEND\xaeB`\x82")
