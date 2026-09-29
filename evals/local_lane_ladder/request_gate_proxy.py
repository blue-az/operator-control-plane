#!/usr/bin/env python3
"""Validating proxy between Pi and the study Ollama endpoint.

Every POST /v1/chat/completions body is checked with
comparison_preflight.validate_request against the contract that owns the
requested model. A body that fails is rejected with HTTP 422 and never reaches
the model, so a comparison run cannot silently use unpinned sampling. Every
verdict is appended to --log (prompts and tool definitions are not copied);
the first passing body per model is saved to --capture-dir for
preflight_comparison.py --request-body.

Other requests (model listing, etc.) are forwarded unchanged.
"""
from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from comparison_preflight import PreflightError, validate_contract, validate_request

HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-length", "host"}


class Gate:
    def __init__(self, contracts: list[dict], upstream: str, log: Path, capture_dir: Path):
        self.by_model: dict[str, dict] = {}
        for contract in contracts:
            validate_contract(contract)
            for tag in contract["models"]:
                if tag in self.by_model:
                    raise PreflightError(f"{tag} appears in more than one contract")
                self.by_model[tag] = contract
        parts = urlsplit(upstream)
        self.host, self.port = parts.hostname, parts.port or 80
        self.log, self.capture_dir = log, capture_dir
        self.lock = threading.Lock()
        capture_dir.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)

    def check(self, body: dict) -> list[str]:
        contract = self.by_model.get(body.get("model"))
        if contract is None:
            return [f"model {body.get('model')!r} is not in any comparison contract"]
        try:
            validate_request(contract, body)
        except PreflightError as exc:
            return [str(exc)]
        return []

    def record(self, body: dict, errors: list[str]) -> None:
        entry = {"ts": time.time(), "model": body.get("model"), "passed": not errors, "errors": errors,
                 "fields": {k: v for k, v in body.items() if k not in ("messages", "tools")}}
        with self.lock:
            with self.log.open("a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
            if not errors:
                target = self.capture_dir / (str(body["model"]).replace(":", "_") + ".json")
                if not target.exists():
                    target.write_text(json.dumps(body, indent=2) + "\n")


def make_handler(gate: Gate):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # close-delimited responses; streams pass straight through

        def log_message(self, fmt, *args):  # keep stdout for verdicts only
            return

        def forward(self, method: str, raw: bytes | None) -> None:
            conn = http.client.HTTPConnection(gate.host, gate.port, timeout=3600)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
            if raw is not None:
                headers["Content-Length"] = str(len(raw))
            conn.request(method, self.path, body=raw, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                if key.lower() not in HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            while chunk := resp.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
            conn.close()

        def reject(self, errors: list[str]) -> None:
            payload = json.dumps({"error": {"message": "request_gate_proxy: " + "; ".join(errors),
                                            "type": "invalid_request_error"}}).encode()
            self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self.forward("GET", None)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.path.rstrip("/").endswith("/chat/completions"):
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    self.reject(["body is not JSON"])
                    return
                errors = gate.check(body)
                gate.record(body, errors)
                print(json.dumps({"model": body.get("model"), "passed": not errors, "errors": errors}), flush=True)
                if errors:
                    self.reject(errors)
                    return
            self.forward("POST", raw)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, action="append", required=True)
    parser.add_argument("--upstream", default="http://127.0.0.1:11444")
    parser.add_argument("--listen-port", type=int, default=11454)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    args = parser.parse_args()
    gate = Gate([json.loads(p.read_text()) for p in args.contract], args.upstream, args.log, args.capture_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.listen_port), make_handler(gate))
    print(f"request gate listening on 127.0.0.1:{args.listen_port} -> {args.upstream}; "
          f"{len(gate.by_model)} contracted models", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
