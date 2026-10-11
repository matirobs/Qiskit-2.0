"""Serve the RePack-Q workbench and its same-origin local Python API."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "src"
WEB_ROOT = (ROOT / "web").resolve()
INDEX_FILE = (ROOT / "index.html").resolve()
MAIN_SCRIPT = (ROOT / "main.js").resolve()
MAIN_STYLES = (ROOT / "styles.css").resolve()
sys.path.insert(0, str(SOURCE_ROOT if (SOURCE_ROOT / "repackq").is_dir() else ROOT))

from repackq.quantum.qiskit_compat import get_capabilities
from repackq.ui import (
    evaluate_selection,
    get_demo_state,
    reveal_future,
    run_classical_comparison,
    run_live_qaoa,
)


MAX_REQUEST_BYTES = 64 * 1024
FUTURE_ASSET_PATHS = {
    "/web/data/demo/future.json",
    "/data/demo/future.json",
    "/repackq-demo-future.json",
}
FUTURE_FIXTURE = (ROOT / "web" / "data" / "demo" / "future.json").resolve()
ROOT_STATIC_ASSETS = {
    (ROOT / name).resolve()
    for name in (
        "repackq-demo-inventory.json",
        "repackq-demo-classical.json",
        "repackq-demo-qaoa-replay.json",
        "repackq-benchmark-summary.json",
        "repackq-benchmark-trials.json",
    )
}
OPTION_NAMES = {
    "horizon_cycles",
    "pack_size_k",
    "objective_mode",
    "annealing_seed",
    "annealing_steps",
    "shots",
    "reps",
    "optimizer_mode",
    "max_evaluations",
}


def _clean_options(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("options must be an object")
    return {key: item for key, item in value.items() if key in OPTION_NAMES}


def _query_options(query: dict[str, list[str]]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for name in ("horizon_cycles", "pack_size_k"):
        if query.get(name):
            parsed[name] = int(query[name][0])
    return parsed


class RePackQHandler(SimpleHTTPRequestHandler):
    """Serve static files and narrowly scoped local API endpoints."""

    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} {format_string % args}", flush=True)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid request length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("request body must be JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _handle_api_error(self, exc: Exception) -> None:
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            # The browser may cancel an in-flight API read while reloading or
            # navigating away. There is no live socket left for an error reply.
            return
        if isinstance(exc, (TypeError, ValueError, KeyError)):
            self._send_json(400, {"error": "invalid_request", "message": str(exc)})
            return
        self.log_error("Local API request failed: %r", exc)
        self._send_json(
            500,
            {"error": type(exc).__name__, "message": "The local Python service could not complete the request."},
        )

    def _serve_workbench_asset(self, method: str) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in FUTURE_ASSET_PATHS:
            self.send_error(404, "Held-out fixture values are available only through the reveal action.")
            return
        if (
            parsed.path not in {"/", "/index.html", "/main.js", "/styles.css", "/web"}
            and not parsed.path.startswith("/web/")
            and parsed.path not in {f"/{path.name}" for path in ROOT_STATIC_ASSETS}
        ):
            self.send_error(404, "This local server only serves the RePack-Q workbench and API.")
            return

        translated = Path(self.translate_path(self.path)).resolve()
        if translated == FUTURE_FIXTURE:
            self.send_error(404, "Held-out fixture values are available only through the reveal action.")
            return
        root_index_request = parsed.path == "/" and translated == ROOT.resolve()
        if not (
            root_index_request
            or translated == INDEX_FILE
            or translated == MAIN_SCRIPT
            or translated == MAIN_STYLES
            or translated in ROOT_STATIC_ASSETS
            or translated == WEB_ROOT
            or WEB_ROOT in translated.parents
        ):
            self.send_error(404, "This local server only serves the RePack-Q workbench and API.")
            return
        getattr(super(), method)()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/capabilities":
            capabilities = get_capabilities()
            capabilities.update({"available": True, "interactive": True, "bridge": "repackq-local-http-v1"})
            self._send_json(200, capabilities)
            return
        if parsed.path == "/api/state":
            try:
                options = _query_options(parse_qs(parsed.query))
                self._send_json(200, get_demo_state(**options))
            except Exception as exc:
                self._handle_api_error(exc)
            return
        self._serve_workbench_asset("do_GET")

    def do_HEAD(self) -> None:
        self._serve_workbench_asset("do_HEAD")

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            options = _clean_options(payload.get("options"))
            if self.path == "/api/evaluate":
                indices = payload.get("selected_indices")
                if not isinstance(indices, list):
                    raise ValueError("selected_indices must be an array")
                result = evaluate_selection(indices, **options)
                self._send_json(200, result)
                return
            if self.path == "/api/classical":
                result = run_classical_comparison(**options)
                self._send_json(200, result)
                return
            if self.path == "/api/future":
                indices = payload.get("selected_indices")
                if not isinstance(indices, list):
                    raise ValueError("selected_indices must be an array")
                reveal_options = {
                    key: options[key]
                    for key in ("horizon_cycles", "pack_size_k")
                    if key in options
                }
                result = reveal_future(indices, **reveal_options)
                self._send_json(200, result)
                return
            if self.path == "/api/qaoa":
                self._stream_qaoa(options)
                return
            self.send_error(404, "Unknown RePack-Q API endpoint.")
        except Exception as exc:
            self._handle_api_error(exc)

    def _stream_qaoa(self, options: dict[str, Any]) -> None:
        options = dict(options)
        # Keep the browser path deterministic and portable; direct callers can
        # still explicitly request COBYLA when their runtime supports it.
        options.setdefault("optimizer_mode", "grid")
        options.setdefault("max_evaluations", 121)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_event(payload: dict[str, Any]) -> None:
            body = (json.dumps(payload, allow_nan=False) + "\n").encode("utf-8")
            self.wfile.write(f"{len(body):X}\r\n".encode("ascii"))
            self.wfile.write(body)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        try:
            result = run_live_qaoa(
                **options,
                on_stage=lambda stage: write_event({"type": "stage", "stage": stage}),
            )
            write_event({"type": "result", "result": result})
        except Exception as exc:
            self.log_error("Local QAOA run failed: %r", exc)
            try:
                write_event({
                    "type": "error",
                    "error": type(exc).__name__,
                    "message": "QAOA could not complete. Classical results remain available.",
                })
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local RePack-Q interactive workbench.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: localhost only)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    args = parser.parse_args()
    # Qiskit's compiled SparsePauliOp simplifier can segfault when QAOA is
    # constructed from a request worker thread in some supported runtimes.
    # This local single-user workbench runs each handler on the server thread;
    # QAOA progress still streams to the active browser request.
    server = HTTPServer((args.host, args.port), RePackQHandler)
    print(f"RePack-Q is running at http://{args.host}:{args.port}/", flush=True)
    print("Press Ctrl+C to stop the local server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("RePack-Q server stopped.", flush=True)


if __name__ == "__main__":
    main()
