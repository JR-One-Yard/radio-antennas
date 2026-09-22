import json
from http.client import HTTPConnection
from threading import Thread

from ism_scanner.cli import _ingest
from ism_scanner.server import Hub, _health, serve_http
from ism_scanner.sources import simulation_lines


def _get(host, port, path):
    connection = HTTPConnection(host, port, timeout=4)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def test_http_snapshot_contains_classified_entities():
    hub = Hub()
    server = serve_http(hub, host="127.0.0.1", port=0)
    host, port = server.server_address
    _ingest(hub, simulation_lines(cycles=2, pause=0), hold_seconds=0.0)
    try:
        status, raw = _get(host, port, "/api/snapshot")
        body = json.loads(raw)
        assert status == 200
        assert body["decoded"] >= 2
        assert body["entity_count"] >= 2
        categories = {entity["category"] for entity in body["entities"]}
        assert "weather" in categories
        assert "tpms" in categories
        names = {entity["name"] for entity in body["entities"]}
        assert "Garden weather · Cotech 53" in names
        assert "Car tyre · Toyota A1B2C3D4" in names
        assert body["digest"]["window_s"] == 3600
        assert body["status"]["health"] in {"ok", "starting", "waiting"}
        assert body["status"]["raw_lines"] > 0
        assert body["status"]["last_line_age_s"] is not None
        assert body["status"]["log"]

        status, html = _get(host, port, "/")
        assert status == 200
        assert "Over the Fence" in html.decode()

        status, digest = _get(host, port, "/api/digest")
        assert status == 200
        assert "entities" in json.loads(digest)

        status, health = _get(host, port, "/api/health")
        assert status == 200
        assert "health" in json.loads(health)
    finally:
        server.shutdown()
        Thread(target=server.server_close, daemon=True).start()


def test_health_reflects_ingest_state():
    assert _health("listening", True, None) == "waiting"
    assert _health("listening", True, 5.0) == "ok"
    assert _health("listening", True, 60.0) == "quiet"
    assert _health("listening", True, 500.0) == "stalled"
    assert _health("listening", False, 1.0) == "dead"
    assert _health("error", True, 1.0) == "dead"
    assert _health("simulating", True, 1.0) == "ok"


def test_status_log_records_message_changes():
    hub = Hub()
    hub.set_status(state="listening", message="Live at 433.92M")
    hub.set_status(state="listening", message="Live at 433.92M")
    hub.set_status(state="error", message="Ingest thread died: boom")
    log = hub.status_view()["log"]
    assert [entry["message"] for entry in log] == [
        "Starting listener",
        "Live at 433.92M",
        "Ingest thread died: boom",
    ]
    assert log[-1]["level"] == "error"
