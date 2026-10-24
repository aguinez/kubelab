"""Webhook que recibe las notificaciones de ArgoCD y lanza la canalizacion.

Antes solo imprimia en el log el nombre de la aplicacion con problemas. Ahora,
ademas de registrarlo, crea un objeto `Workflow` a partir del WorkflowTemplate
`argocd-diagnose` (namespace `argo`), pasandole el nombre de la application como
parametro. Ese workflow es la canalizacion de diagnostico.

Se habla directamente con el API server de Kubernetes (in-cluster) usando el
token del ServiceAccount montado, sin depender de kubectl.

Evita acumular el mismo problema: si ya hay un Workflow activo (Pending/Running)
para la misma application, no lanza otro.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
ARGO_NAMESPACE = os.environ.get("ARGO_NAMESPACE", "argo")
WORKFLOW_TEMPLATE = os.environ.get("WORKFLOW_TEMPLATE", "argocd-diagnose")
LABEL_KEY = os.environ.get("WORKFLOW_LABEL_KEY", "kubelab.io/app")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "10"))

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
ACTIVE_PHASES = ("", "Pending", "Running")


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


# --- API de Kubernetes (in-cluster) ------------------------------------------


def _api_base():
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    if not host:
        return None
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    return f"https://{host}:{port}"


def _ssl_context():
    cafile = os.path.join(SA_DIR, "ca.crt")
    if os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def _token():
    with open(os.path.join(SA_DIR, "token"), encoding="utf-8") as fh:
        return fh.read().strip()


def k8s_request(method, path, body=None):
    base = _api_base()
    if not base:
        raise RuntimeError("no hay variables in-cluster (KUBERNETES_SERVICE_HOST)")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=REQUEST_TIMEOUT) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def workflows_path():
    return f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NAMESPACE}/workflows"


def active_workflow_exists(app_name):
    selector = urllib.parse.quote(f"{LABEL_KEY}={app_name}")
    data = k8s_request("GET", f"{workflows_path()}?labelSelector={selector}")
    for item in data.get("items", []):
        phase = (item.get("status") or {}).get("phase", "")
        if phase in ACTIVE_PHASES:
            return item.get("metadata", {}).get("name")
    return None


def create_workflow(app_name):
    body = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": f"{WORKFLOW_TEMPLATE}-",
            "namespace": ARGO_NAMESPACE,
            "labels": {"app": WORKFLOW_TEMPLATE, LABEL_KEY: app_name},
        },
        "spec": {
            "workflowTemplateRef": {"name": WORKFLOW_TEMPLATE},
            "arguments": {"parameters": [{"name": "app", "value": app_name}]},
        },
    }
    created = k8s_request("POST", workflows_path(), body)
    return created.get("metadata", {}).get("name")


def trigger_pipeline(app_name):
    """Devuelve (accion, detalle) segun lo que haya ocurrido."""
    existing = active_workflow_exists(app_name)
    if existing:
        return "skipped", existing
    return "created", create_workflow(app_name)


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
        self._respond(200, {"status": "ok", "workflowTemplate": WORKFLOW_TEMPLATE, "namespace": ARGO_NAMESPACE})

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
            action, detail = trigger_pipeline(app_name)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as exc:
            message = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, urllib.error.HTTPError):
                message += f" ({exc.read().decode('utf-8', 'replace')})"
            print(f"[webhook] fallo al lanzar el workflow: {message}", flush=True)
            self._respond(502, {"app": app_name, "error": message})
            return

        if action == "skipped":
            print(f"[webhook] ya hay un workflow activo para {app_name} ({detail}), no se lanza otro", flush=True)
        else:
            print(f"[webhook] workflow lanzado para {app_name}: {detail}", flush=True)
        self._respond(200, {"app": app_name, "action": action, "workflow": detail})

    def log_message(self, fmt, *args):
        sys.stdout.write("[webhook] " + (fmt % args) + "\n")
        sys.stdout.flush()


def main():
    print(f"[webhook] listening on 0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
