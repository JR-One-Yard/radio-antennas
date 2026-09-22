from pathlib import Path

from meteor_lease.host import load_host, resolve_bind
from meteor_lease.radio import find_satdump


def test_load_host_defaults_without_file(tmp_path: Path, monkeypatch):
    from meteor_lease import host as hostmod

    monkeypatch.setattr(hostmod, "HOST_FILE", tmp_path / "missing.json")
    data = load_host(tmp_path / "missing.json")
    assert data["idle"] == "ism-scan"
    assert data["bind"] == "127.0.0.1"


def test_load_host_dump1090(tmp_path: Path):
    path = tmp_path / "host.json"
    path.write_text('{"idle":"dump1090","bind":"100.64.0.2","planes_port":10900}\n')
    data = load_host(path)
    assert data["idle"] == "dump1090"
    assert data["bind"] == "100.64.0.2"
    assert data["planes_port"] == 10900


def test_load_host_rejects_unknown_idle(tmp_path: Path):
    path = tmp_path / "host.json"
    path.write_text('{"idle":"both"}\n')
    assert load_host(path)["idle"] == "ism-scan"


def test_planes_url_https_when_magicdns(monkeypatch):
    from meteor_lease import host as hostmod

    monkeypatch.setattr(hostmod, "_tailscale_dns", lambda: "the-mini.example.ts.net")
    url = hostmod.planes_url({"planes_port": 10900, "bind": "127.0.0.1", "census_port": 4330})
    assert url == "https://the-mini.example.ts.net:10900/"
    try:
        resolve_bind({"bind": "0.0.0.0", "planes_port": 10900, "census_port": 4330})
    except ValueError as error:
        assert "all interfaces" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_find_satdump_prefers_app(tmp_path: Path, monkeypatch):
    from meteor_lease import paths as pathsmod
    from meteor_lease import radio as radiomod

    app = tmp_path / "SatDump.app" / "Contents" / "MacOS" / "satdump"
    app.parent.mkdir(parents=True)
    app.write_text("fake")
    brew = tmp_path / "brew-satdump"
    brew.write_text("brew")
    monkeypatch.setattr(radiomod, "SATDUMP_APP", app)
    monkeypatch.setattr(pathsmod, "SATDUMP_APP", app)
    monkeypatch.setattr(radiomod.shutil, "which", lambda _n: str(brew))
    assert find_satdump() == app
