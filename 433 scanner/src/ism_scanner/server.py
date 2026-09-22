from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ism_scanner.census import Census

STATIC = Path(__file__).resolve().parent / "static"

# How long rtl_433 may stay silent (no bytes on either descriptor) before the UI
# is told the ingest looks wedged. With -A on live RF the analyser chatters
# constantly, so even a quiet street produces lines well inside this window.
QUIET_AFTER_S = 45.0
STALLED_AFTER_S = 120.0


class Hub:
    def __init__(self) -> None:
        self.census = Census()
        self.status: dict[str, Any] = {
            "state": "starting",
            "source": None,
            "frequency": "433.92M",
            "message": "Starting listener",
            "workaround": None,
            "raw_lines": 0,
            "last_line_at": None,
            "last_line_age_s": None,
            "ingest_alive": None,
            "health": "starting",
            "radio_owner": None,
            "capture": None,
            "log": [],
        }
        self._log: deque[dict[str, str]] = deque(maxlen=40)
        self._last_line_monotonic: float | None = None
        self._ingest_thread: threading.Thread | None = None
        self._listeners: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self.log("Starting listener")

    # -- status -------------------------------------------------------------

    def set_status(self, **fields: Any) -> None:
        with self._lock:
            message = fields.get("message")
            if message and message != self.status.get("message"):
                state = fields.get("state")
                level = (
                    "error"
                    if state == "error"
                    else "warn"
                    if fields.get("workaround") or fields.get("radio_owner")
                    else "info"
                )
                self._append_log(str(message), level=level)
            self.status.update(fields)

    def log(self, message: str, *, level: str = "info") -> None:
        with self._lock:
            self._append_log(message, level=level)

    def _append_log(self, message: str, *, level: str) -> None:
        self._log.append(
            {
                "time": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "level": level,
                "message": message,
            }
        )

    def saw_line(self, raw_lines: int) -> None:
        with self._lock:
            self._last_line_monotonic = time.monotonic()
            self.status["raw_lines"] = raw_lines
            self.status["last_line_at"] = (
                datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )

    def attach_ingest(self, thread: threading.Thread) -> None:
        with self._lock:
            self._ingest_thread = thread

    def _status_view(self) -> dict[str, Any]:
        body = dict(self.status)
        alive = self._ingest_thread.is_alive() if self._ingest_thread else None
        body["ingest_alive"] = alive
        age = (
            time.monotonic() - self._last_line_monotonic
            if self._last_line_monotonic is not None
            else None
        )
        body["last_line_age_s"] = round(age, 1) if age is not None else None
        body["health"] = _health(body["state"], alive, age)
        body["log"] = list(self._log)[-12:]
        return body

    # -- sightings ----------------------------------------------------------

    def publish(self, sighting: dict[str, Any]) -> None:
        with self._lock:
            entity = self.census.ingest(sighting)
            listeners = list(self._listeners)
        message = {"sighting": sighting, "entity": entity}
        for listener in listeners:
            try:
                listener.put_nowait(message)
            except queue.Full:
                with listener.mutex:
                    listener.queue.clear()
                with suppress(queue.Full):
                    listener.put_nowait(message)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            body = self.census.snapshot()
            body["status"] = self._status_view()
            return body

    def status_view(self) -> dict[str, Any]:
        with self._lock:
            return self._status_view()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        listener: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        with self._lock:
            self._listeners.append(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)


def _health(state: str, alive: bool | None, age: float | None) -> str:
    if state == "error" or alive is False:
        return "dead"
    if state in {"starting", "idle"}:
        return state
    if state == "listening":
        if age is None:
            return "waiting"
        if age > STALLED_AFTER_S:
            return "stalled"
        if age > QUIET_AFTER_S:
            return "quiet"
    return "ok"


def make_handler(hub: Hub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._file(STATIC / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/api/snapshot":
                self._json(hub.snapshot())
                return
            if parsed.path in {"/api/status", "/api/health"}:
                self._json(hub.status_view())
                return
            if parsed.path == "/api/digest":
                with hub._lock:
                    self._json(hub.census.digest())
                return
            if parsed.path == "/api/events":
                self._sse()
                return
            self.send_error(404, "Not found")

        def _file(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self.send_error(404, "Not found")
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _sse(self) -> None:
            listener = hub.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                snapshot = hub.snapshot()
                self.wfile.write(f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        message = listener.get(timeout=10)
                    except queue.Empty:
                        status = json.dumps(hub.status_view())
                        self.wfile.write(f"event: status\ndata: {status}\n\n".encode())
                        self.wfile.flush()
                        continue
                    self.wfile.write(f"event: heard\ndata: {json.dumps(message)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            finally:
                hub.unsubscribe(listener)

    return Handler


def serve_http(hub: Hub, *, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(hub))
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="ism-http")
    thread.start()
    return server
