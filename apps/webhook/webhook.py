import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8080"))


def extract_app_name(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("app", "application", "appName", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    nested = payload.get("app")
    if isinstance(nested, dict):
        metadata = nested.get("metadata") or {}
        return metadata.get("name")
    return None


class Handler(BaseHTTPRequestHandler):
    def _respond(self, code, body=b"ok\n"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return ""
        return self.rfile.read(length).decode("utf-8", "replace")

    def do_GET(self):
        self._respond(200, b"webhook ready\n")

    def do_POST(self):
        raw = self._read_body()
        print(f"[webhook] received payload: {raw}", flush=True)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        app_name = extract_app_name(payload)
        if app_name:
            print(f"[webhook] application with problems: {app_name}", flush=True)
        else:
            print("[webhook] could not determine application name", flush=True)
        self._respond(200)

    def log_message(self, fmt, *args):
        sys.stdout.write("[webhook] " + (fmt % args) + "\n")
        sys.stdout.flush()


def main():
    print(f"[webhook] listening on 0.0.0.0:{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
