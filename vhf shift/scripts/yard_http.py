#!/usr/bin/env python3
"""Serve the plane map and capture PNGs on one Tailscale-bound address."""

from __future__ import annotations

import argparse
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=10900)
    parser.add_argument("--planes", required=True)
    parser.add_argument("--captures", required=True)
    args = parser.parse_args(argv)
    if args.bind in {"0.0.0.0", "::", "*"}:
        print("refusing to bind all interfaces; pass a Tailscale IPv4", file=sys.stderr)
        return 2
    planes = Path(args.planes).resolve()
    captures = Path(args.captures).resolve()
    planes.mkdir(parents=True, exist_ok=True)
    captures.mkdir(parents=True, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            raw = unquote(urlparse(path).path)
            if raw == "/captures" or raw.startswith("/captures/"):
                rest = raw[len("/captures") :].lstrip("/")
                return str(_under(captures, rest))
            rel = raw.lstrip("/") or "index.html"
            return str(_under(planes, rel))

        def log_message(self, fmt: str, *log_args) -> None:
            sys.stderr.write(f"{self.address_string()} - {fmt % log_args}\n")

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"yard-http {args.bind}:{args.port} planes={planes} captures={captures}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def _under(root: Path, rest: str) -> Path:
    target = (root / rest).resolve()
    if root != target and root not in target.parents:
        return root / "index.html"
    return target


if __name__ == "__main__":
    raise SystemExit(main())
