"""Webhook que recibe las notificaciones de ArgoCD y arranca el proceso en n8n.

Antes este webhook imprimia el nombre de la aplicacion con problemas y creaba un
Workflow de Argo. Ahora el orquestador es n8n: al recibir la notificacion hace
POST al webhook del workflow `argocd-diagnostic`, que corre el diagnostico
(argocd-diagnostician) y un paso LLM que redacta el correo de diagnostico.

El correo NO se envia (en el lab no hay API de correo): n8n lo devuelve en la
respuesta, este webhook lo registra en su log y ademas queda visible en la
ejecucion dentro de la UI de n8n.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
N8N_WEBHOOK_URL = os.environ.get(
    "N8N_WEBHOOK_URL",
    "http://n8n.apps.svc.cluster.local/webhook/argocd-diagnostic",
)
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "90"))


def extract_app_name(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("app", "application", "appName", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            metadata = value.get("metadata") or {}
            if metadata.get("name"):
                return metadata["name"]
    return None


def trigger_n8n(payload):
    """Arranca el workflow de n8n y devuelve (status, json) de su respuesta."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        N8N_WEBHOOK_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read()
        return response.status, (json.loads(raw) if raw else {})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return ""
        return self.rfile.read(length).decode("utf-8", "replace")

    def do_GET(self):
        self._respond(200, {"status": "ok", "n8nWebhook": N8N_WEBHOOK_URL})

    def do_POST(self):
        raw = self._read_body()
        print(f"[webhook] received payload: {raw}", flush=True)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        app_name = extract_app_name(payload)
        if not app_name:
            print("[webhook] could not determine application name", flush=True)
            self._respond(400, {"error": "no se pudo determinar el nombre de la application"})
            return

        print(f"[webhook] application with problems: {app_name}", flush=True)
        try:
            status, draft = trigger_n8n(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            message = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, urllib.error.HTTPError):
                message += f" ({exc.read().decode('utf-8', 'replace')})"
            print(f"[webhook] fallo al arrancar n8n: {message}", flush=True)
            self._respond(502, {"app": app_name, "error": message})
            return

        print(f"[webhook] n8n respondio {status}", flush=True)
        print(
            "[webhook] correo de diagnostico redactado (NO enviado):\n"
            + json.dumps(draft, indent=2, ensure_ascii=False),
            flush=True,
        )
        self._respond(200, {"app": app_name, "n8nStatus": status, "email": draft})

    def log_message(self, fmt, *args):
        sys.stdout.write("[webhook] " + (fmt % args) + "\n")
        sys.stdout.flush()


def main():
    print(f"[webhook] listening on 0.0.0.0:{PORT}", flush=True)
    print(f"[webhook] n8n webhook: {N8N_WEBHOOK_URL}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
