import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FAIL_AFTER_SECONDS = int(os.environ.get("FAIL_AFTER_SECONDS", "30"))
PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stdout.write("[app-error-test] " + (fmt % args) + "\n")
        sys.stdout.flush()


def fail():
    print(
        f"[app-error-test] simulated failure after {FAIL_AFTER_SECONDS}s",
        flush=True,
    )
    os._exit(1)


def main():
    print(
        f"[app-error-test] started, will fail after {FAIL_AFTER_SECONDS}s",
        flush=True,
    )
    threading.Timer(FAIL_AFTER_SECONDS, fail).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
