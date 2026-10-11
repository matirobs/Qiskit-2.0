"""Serve the dashboard on localhost using the Python standard library."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .service import DashboardService, ROOT

ASSETS = Path(__file__).parent / "web"


def make_handler(service):
    """Connect dashboard requests to the local service."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            if len(args) > 1 and str(args[1]) != "200":
                super().log_message(format, *args)

        def send(self, status, payload, content_type="application/json; charset=utf-8"):
            body = json.dumps(payload, allow_nan=False).encode() if isinstance(payload, (dict, list)) else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            port = self.server.server_address[1]
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Local access only"})
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/api/bootstrap":
                    return self.send(200, service.bootstrap())
                if parsed.path == "/api/problem":
                    token = parse_qs(parsed.query).get("trial_id", [""])[0]
                    return self.send(200, service.export_problem(token))
                # serve only dashboard assets, never arbitrary project paths
                assets = {"/": ("index.html", "text/html"), "/styles.css": ("styles.css", "text/css"),
                          "/app.js": ("app.js", "text/javascript"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if parsed.path not in assets:
                    return self.send(404, {"error": "Not found"})
                name, content_type = assets[parsed.path]
                return self.send(200, (ASSETS / name).read_bytes(), content_type + "; charset=utf-8")
            except (ValueError, KeyError) as error:
                return self.send(400, {"error": str(error)})

        def do_POST(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Local access only"})
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://{self.headers.get('Host')}",):
                return self.send(403, {"error": "Cross-origin requests are not accepted"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    return self.send(413, {"error": "Request must contain a small JSON object"})
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Request must be an object")
                if self.path == "/api/trial":
                    return self.send(200, service.create_trial(payload))
                if self.path == "/api/reveal":
                    return self.send(200, service.reveal(payload.get("trial_id", "")))
                if self.path == "/api/manual":
                    return self.send(200, service.manual(payload.get("trial_id", ""), payload.get("indices", [])))
                return self.send(404, {"error": "Not found"})
            except (ValueError, KeyError, TypeError) as error:
                return self.send(400, {"error": str(error)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Open the local RePack-Q battery workbench.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--synthetic", action="store_true", help="Use clearly labeled illustrative sample inputs")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=Path, default=ROOT / "models/capacity_model.json")
    parser.add_argument("--data", type=Path, default=ROOT / "data/processed/cell_histories.json")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between zero and 65535")
    try:
        service = DashboardService(synthetic=args.synthetic, model_path=args.model, data_path=args.data)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"RePack-Q workbench: {url}", flush=True)
    print("Data: " + ("illustrative sample inputs" if service.synthetic else "real cached battery histories"), flush=True)
    print(service.bootstrap()["quantum"]["message"] + ". Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
