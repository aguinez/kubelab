#!/usr/bin/env python3
"""ArgoCD application diagnostician.

Servicio que recibe el nombre de una ArgoCD Application y recolecta la
informacion necesaria para entender que esta fallando, usando kubectl contra el
mismo cluster donde corre.

Flujo (equivale al "primer paso" de la canalizacion de Argo Workflows):

  1. Lee el objeto Application   -> kubectl get application <app> -n argocd -o json
  2. Recorre los objetos que la componen (status.resources) y selecciona los que
     estan degradados / fuera de sync (pods, deployments, replicasets, ...).
  3. Recolecta evidencia de cada uno con kubectl:
        - get <kind> <name> -o json
        - describe <kind> <name>
        - logs (actuales y previos) de los pods
        - eventos relacionados
  4. Reduce la evidencia cruda a un conjunto pequeno de firmas unicas
     (normalizando timestamps, ids y numeros) para NO acumular el mismo error
     repetido N veces.
  5. Prepara un "request adicional" (metodo, headers, body) hacia un endpoint de
     reporte que todavia NO esta definido (REPORT_ENDPOINT). Si el endpoint esta
     configurado, se envia; si no, solo se prepara y se deja en el informe.

Modos:
  * servidor (default): HTTP server con GET/POST /diagnose (lo expone el Deployment)
  * cli:                 diagnostician.py --app NAME [--output FILE]
  * via-service:         diagnostician.py --via-service URL --app NAME [--output FILE]
                         (primer paso de la canalizacion: delega en el Deployment)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

PORT = int(os.environ.get("PORT", "8080"))
ARGOCD_NAMESPACE = os.environ.get("ARGOCD_NAMESPACE", "argocd")
REPORT_ENDPOINT = os.environ.get("REPORT_ENDPOINT", "").strip()
REPORT_METHOD = os.environ.get("REPORT_METHOD", "POST").strip().upper()
REPORT_TIMEOUT = int(os.environ.get("REPORT_TIMEOUT", "10"))
KUBECTL_BIN = os.environ.get("KUBECTL_BIN", "kubectl")
KUBECTL_TIMEOUT = int(os.environ.get("KUBECTL_TIMEOUT", "25"))
MAX_LOG_LINES = int(os.environ.get("MAX_LOG_LINES", "200"))
MAX_SIGNATURES = int(os.environ.get("MAX_SIGNATURES", "25"))
MAX_SIGNATURE_LEN = int(os.environ.get("MAX_SIGNATURE_LEN", "220"))
MAX_RESOURCES = int(os.environ.get("MAX_RESOURCES", "40"))

WORKLOAD_KINDS = {
    "Deployment",
    "ReplicaSet",
    "StatefulSet",
    "DaemonSet",
    "Pod",
    "Job",
    "CronJob",
}

# --- Firmas: normalizacion y categorizacion ---------------------------------

TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b")
NUM_RE = re.compile(r"\b\d+(?:\.\d+)?(?:[a-zA-Z]{1,3})?\b")
WS_RE = re.compile(r"\s+")

CATEGORIES = [
    ("ImagePullBackOff", re.compile(r"ImagePullBackOff|ErrImagePull|ErrImageNeverPull|manifest unknown", re.I)),
    ("CrashLoopBackOff", re.compile(r"CrashLoopBackOff|Back-off restarting failed container", re.I)),
    ("OOMKilled", re.compile(r"OOMKilled|out of memory", re.I)),
    ("ProgressDeadlineExceeded", re.compile(r"ProgressDeadlineExceeded", re.I)),
    ("FailedScheduling", re.compile(r"FailedScheduling|Insufficient (cpu|memory)|nodes are available", re.I)),
    ("ProbeFailed", re.compile(r"(Readiness|Liveness|Startup) probe failed", re.I)),
    ("ContainerExit", re.compile(r"exit code|Error \(exit", re.I)),
    ("FailedMount", re.compile(r"FailedMount|Unable to attach or mount", re.I)),
    ("ConfigError", re.compile(r"CreateContainerConfigError|CreateContainerError|InvalidImageName", re.I)),
    ("Evicted", re.compile(r"Evicted|DiskPressure|node was low on resource", re.I)),
    ("Forbidden", re.compile(r"forbidden|unauthorized|permission denied", re.I)),
]


def categorize(text):
    for name, rx in CATEGORIES:
        if rx.search(text):
            return name
    return "Other"


def normalize(text):
    """Colapsa variabilidad (timestamps, ids, numeros) para deduplicar."""
    s = TIMESTAMP_RE.sub("", text.strip())
    s = HEX_RE.sub("<id>", s)
    s = NUM_RE.sub("<n>", s)
    s = WS_RE.sub(" ", s)
    return s.strip(" :-\t")[:MAX_SIGNATURE_LEN]


class SignatureBucket:
    """Acumula lineas crudas y las reduce a firmas unicas con conteo."""

    def __init__(self, cap):
        self.cap = cap
        self._items = OrderedDict()

    def add(self, source, raw):
        raw = (raw or "").strip()
        if not raw:
            return
        sig = normalize(raw)
        if len(sig) < 4:
            return
        entry = self._items.get(sig)
        if entry is None:
            entry = {
                "signature": sig,
                "category": categorize(raw),
                "count": 0,
                "sources": Counter(),
                "example": raw[:MAX_SIGNATURE_LEN],
            }
            self._items[sig] = entry
        entry["count"] += 1
        entry["sources"][source] += 1

    def add_text(self, source, text, only_relevant=False):
        if not text:
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if only_relevant and not RELEVANT_RE.search(line):
                continue
            self.add(source, line)

    def result(self):
        items = sorted(self._items.values(), key=lambda e: (-e["count"], e["signature"]))
        items = items[: self.cap]
        for entry in items:
            entry["sources"] = dict(entry["sources"])
        return items


RELEVANT_RE = re.compile(
    r"(^|\s)(warning|error)\b|failed|back-?off|unhealthy|timeout|exceeded|killed|"
    r"forbidden|denied|oom|crash|evicted|no space|unavailable|invalid|not found|"
    r"exit code|permission denied|refused",
    re.I,
)


# --- kubectl -----------------------------------------------------------------


class KubectlError(RuntimeError):
    pass


def kubectl(args, timeout=KUBECTL_TIMEOUT):
    try:
        return subprocess.run(
            [KUBECTL_BIN, *args], capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise KubectlError(f"kubectl no encontrado: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise KubectlError(f"timeout de kubectl: {' '.join(args)}") from exc


def kubectl_json(args, timeout=KUBECTL_TIMEOUT):
    proc = kubectl([*args, "-o", "json"], timeout=timeout)
    if proc.returncode != 0:
        raise KubectlError(proc.stderr.strip() or f"kubectl {' '.join(args)} fallo")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise KubectlError(f"json invalido de kubectl: {exc}") from exc


def ensure_kubeconfig():
    """Genera un kubeconfig a partir del ServiceAccount si corremos in-cluster."""
    if os.environ.get("KUBECONFIG"):
        return
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    if not host:
        return
    sa = "/var/run/secrets/kubernetes.io/serviceaccount"
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": "in-cluster",
                "cluster": {
                    "certificate-authority": f"{sa}/ca.crt",
                    "server": f"https://{host}:{port}",
                },
            }
        ],
        "users": [{"name": "sa", "user": {"tokenFile": f"{sa}/token"}}],
        "contexts": [
            {
                "name": "in-cluster",
                "context": {"cluster": "in-cluster", "user": "sa"},
            }
        ],
        "current-context": "in-cluster",
    }
    path = "/tmp/kubeconfig"
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
        os.environ["KUBECONFIG"] = path
    except OSError:
        pass


# --- Recoleccion de evidencia ------------------------------------------------


def events_for(namespace, name):
    try:
        data = kubectl_json(
            ["get", "events", "-n", namespace, "--field-selector", f"involvedObject.name={name}"]
        )
    except KubectlError:
        return []
    out = []
    for event in data.get("items", []):
        out.append(f"{event.get('type')} {event.get('reason')}: {event.get('message')}")
    return out


def pod_logs(pod, namespace, bucket):
    found = False
    for previous in (False, True):
        args = ["logs", pod, "-n", namespace, f"--tail={MAX_LOG_LINES}"]
        if previous:
            args.append("--previous")
        proc = kubectl(args)
        if proc.returncode == 0 and proc.stdout.strip():
            label = "previous" if previous else "current"
            bucket.add_text(f"log/{pod}/{label}", proc.stdout)
            found = True
    return found


def inspect_pod(pod, namespace, bucket):
    try:
        obj = kubectl_json(["get", "pod", pod, "-n", namespace])
    except KubectlError as exc:
        bucket.add(f"pod/{pod}", f"no se pudo leer el pod: {exc}")
        return {}
    status = obj.get("status", {}) or {}
    info = {"phase": status.get("phase"), "restarts": {}, "pod": pod}
    for cs in status.get("containerStatuses", []) or []:
        name = cs.get("name")
        restarts = cs.get("restartCount", 0)
        info["restarts"][name] = restarts
        state = cs.get("state", {}) or {}
        waiting = state.get("waiting")
        if waiting:
            bucket.add(f"pod/{pod}", f"{name} waiting: {waiting.get('reason')} {waiting.get('message')}")
        terminated = state.get("terminated") or (cs.get("lastState", {}) or {}).get("terminated")
        if terminated:
            bucket.add(
                f"pod/{pod}",
                f"{name} terminated: {terminated.get('reason')} exit={terminated.get('exitCode')} {terminated.get('message')}",
            )
        if restarts:
            bucket.add(f"pod/{pod}", f"{name} reinicios de contenedor: {restarts}")
    for event in events_for(namespace, pod):
        bucket.add(f"event/{pod}", event)
    bucket.add_text(f"describe/pod/{pod}", kubectl(["describe", "pod", pod, "-n", namespace]).stdout, only_relevant=True)
    pod_logs(pod, namespace, bucket)
    return info


def selector_for(kind, obj):
    if kind in ("Deployment", "ReplicaSet", "StatefulSet", "DaemonSet"):
        return ((obj.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    return {}


def pods_for(kind, name, namespace, obj):
    if kind == "Pod":
        return [name]
    labels = selector_for(kind, obj)
    if not labels:
        return []
    label = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    try:
        data = kubectl_json(["get", "pods", "-n", namespace, "-l", label])
    except KubectlError:
        return []
    return [item["metadata"]["name"] for item in data.get("items", [])]


def workload_unhealthy(kind, obj):
    """Determina si un workload esta fallando a partir de su propio status.

    ArgoCD (>= v3) expone la salud por recurso desde el "app tree" y no siempre
    en status.resources; por eso la salud se calcula aqui con kubectl.
    """
    status = obj.get("status", {}) or {}
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"):
        spec = obj.get("spec", {}) or {}
        desired = spec.get("replicas")
        if desired is None:
            desired = status.get("replicas") or 0
        ready = status.get("readyReplicas") or 0
        unavailable = status.get("unavailableReplicas") or 0
        if unavailable:
            return True, f"unavailableReplicas={unavailable}"
        if desired and ready < desired:
            return True, f"readyReplicas {ready}/{desired}"
        for condition in status.get("conditions", []) or []:
            if condition.get("status") == "False" and condition.get("type") in (
                "Available",
                "Progressing",
                "ReplicaFailure",
            ):
                return True, f"{condition.get('type')}={condition.get('reason')}"
        return False, None
    if kind == "Pod":
        phase = status.get("phase")
        if phase not in ("Running", "Succeeded"):
            return True, f"phase={phase}"
        for cs in status.get("containerStatuses", []) or []:
            if not cs.get("ready") or (cs.get("restartCount") or 0) > 0:
                return True, "contenedor no listo o con reinicios"
        return False, None
    if kind in ("Job", "CronJob"):
        if (status.get("failed") or 0) > 0:
            return True, f"failed={status.get('failed')}"
        conditions = status.get("conditions", []) or []
        for condition in conditions:
            if condition.get("type") == "Failed":
                return True, "Job Failed"
        return False, None
    return False, None


def inspect_workload(kind, name, namespace, bucket, obj=None):
    detail = {"workload": f"{kind}/{name}"}
    if obj is None:
        try:
            obj = kubectl_json(["get", kind, name, "-n", namespace])
        except KubectlError as exc:
            bucket.add(f"{kind}/{name}", f"no se pudo leer el objeto: {exc}")
            return {"error": str(exc)}

    template = (obj.get("spec") or {}).get("template") or {}
    container_specs = (template.get("spec") or {}).get("containers", []) if kind != "Pod" else (obj.get("spec") or {}).get("containers", [])
    detail["images"] = [c.get("image") for c in container_specs]

    if kind != "Pod":
        status = obj.get("status", {}) or {}
        detail["replicas"] = {
            "desired": (obj.get("spec") or {}).get("replicas"),
            "ready": status.get("readyReplicas"),
            "available": status.get("availableReplicas"),
            "unavailable": status.get("unavailableReplicas"),
        }
        for condition in status.get("conditions", []) or []:
            bucket.add(
                f"condition/{kind}/{name}",
                f"{condition.get('type')}={condition.get('status')} {condition.get('reason')}: {condition.get('message')}",
            )
        bucket.add_text(
            f"describe/{kind}/{name}",
            kubectl(["describe", kind, name, "-n", namespace]).stdout,
            only_relevant=True,
        )

    bucket.add_text(f"events/{name}", "\n".join(events_for(namespace, name)))

    pods = pods_for(kind, name, namespace, obj)
    detail["pods"] = pods
    for pod in pods:
        inspect_pod(pod, namespace, bucket)
    return detail


# --- Informe y request adicional ---------------------------------------------


def out_of_sync(sync):
    return sync not in (None, "", "Synced")


def build_forward(report):
    """Prepara (y opcionalmente envia) el request hacia el endpoint aun no definido."""
    body = {k: v for k, v in report.items() if k != "forward"}
    forward = {
        "defined": bool(REPORT_ENDPOINT),
        "endpoint": REPORT_ENDPOINT or None,
        "method": REPORT_METHOD,
        "headers": {"Content-Type": "application/json"},
        "body": body,
        "delivered": False,
    }
    if not REPORT_ENDPOINT:
        forward["note"] = (
            "endpoint aun no definido (REPORT_ENDPOINT vacio): el request se prepara "
            "pero no se envia"
        )
        return forward
    try:
        request = urllib.request.Request(
            REPORT_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            method=REPORT_METHOD,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=REPORT_TIMEOUT) as response:
            forward["delivered"] = True
            forward["status"] = response.status
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        forward["delivered"] = False
        forward["error"] = f"{type(exc).__name__}: {exc}"
    return forward


def diagnose(application_name, argocd_namespace=ARGOCD_NAMESPACE):
    bucket = SignatureBucket(MAX_SIGNATURES)
    application = kubectl_json(["get", "application", application_name, "-n", argocd_namespace])
    status = application.get("status", {}) or {}
    health = (status.get("health") or {}).get("status") or "Unknown"
    sync = (status.get("sync") or {}).get("status") or "Unknown"
    resources = status.get("resources") or []

    inspected = []
    unhealthy = 0
    for res in resources[:MAX_RESOURCES]:
        kind = res.get("kind")
        name = res.get("name")
        namespace = res.get("namespace")
        res_health = (res.get("health") or {}).get("status")
        res_sync = res.get("status")
        entry = {
            "kind": kind,
            "name": name,
            "namespace": namespace,
            "health": res_health,
            "sync": res_sync,
        }
        relevant = False
        if kind in WORKLOAD_KINDS and namespace:
            try:
                obj = kubectl_json(["get", kind, name, "-n", namespace])
            except KubectlError as exc:
                entry["error"] = str(exc)
                inspected.append(entry)
                unhealthy += 1
                continue
            relevant, reason = workload_unhealthy(kind, obj)
            if relevant:
                try:
                    entry.update(inspect_workload(kind, name, namespace, bucket, obj))
                except KubectlError as exc:
                    entry["error"] = str(exc)
        elif out_of_sync(res_sync) or (res_health not in (None, "", "Healthy")):
            relevant = True
            entry["note"] = "recurso fuera de sync o degradado (sin inspeccion de workload)"
        if not relevant:
            continue
        unhealthy += 1
        inspected.append(entry)

    signatures = bucket.result()
    report = {
        "application": application_name,
        "argocdNamespace": argocd_namespace,
        "health": health,
        "sync": sync,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "analyzedResources": len(resources),
        "unhealthyResources": unhealthy,
        "signatureCount": len(signatures),
        "categories": dict(Counter(s["category"] for s in signatures)),
        "signatures": signatures,
        "resources": inspected,
    }
    report["forward"] = build_forward(report)
    return report


# --- HTTP server -------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "argocd-diagnostician/1.0.0"

    def _json(self, code, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {"_raw": raw}

    def _run(self, application_name):
        if not application_name:
            self._json(400, {"error": "falta el nombre de la Application ('app')"})
            return
        print(f"[diagnostician] diagnosticando application: {application_name}", flush=True)
        try:
            report = diagnose(application_name)
        except KubectlError as exc:
            self._json(502, {"application": application_name, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - se reporta cualquier fallo al caller
            self._json(500, {"application": application_name, "error": f"{type(exc).__name__}: {exc}"})
            return
        print(
            f"[diagnostician] {application_name}: health={report['health']} "
            f"firmas={report['signatureCount']} forward_defined={report['forward']['defined']}",
            flush=True,
        )
        self._json(200, report)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/", "/info"):
            self._json(
                200,
                {
                    "service": "argocd-diagnostician",
                    "endpoints": ["GET /healthz", "GET /diagnose?app=NAME", "POST /diagnose"],
                    "reportEndpointDefined": bool(REPORT_ENDPOINT),
                },
            )
            return
        if path == "/healthz":
            self._json(200, {"status": "ok"})
            return
        if path == "/diagnose":
            query = parse_qs(parsed.query)
            self._run((query.get("app") or [""])[0])
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path != "/diagnose":
            self._json(404, {"error": "not found"})
            return
        body = self._read_body()
        query = parse_qs(parsed.query)
        app_name = body.get("app") or (query.get("app") or [""])[0]
        self._run(app_name)

    def log_message(self, fmt, *args):
        sys.stdout.write("[diagnostician] " + (fmt % args) + "\n")
        sys.stdout.flush()


def call_service(base_url, application_name, timeout=KUBECTL_TIMEOUT):
    """Pide el diagnostico al Deployment (a traves de su Service).

    Se usa como primer paso de la canalizacion de Argo Workflows: en vez de
    repetir la logica dentro del pod del workflow, el paso invoca al Deployment
    que ya tiene los RBAC y hace la recoleccion.
    """
    url = f"{base_url.rstrip('/')}/diagnose?app={quote(application_name)}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="ArgoCD application diagnostician")
    parser.add_argument("--app", help="nombre de la ArgoCD Application a diagnosticar")
    parser.add_argument("--output", help="escribir el informe JSON en este archivo")
    parser.add_argument("--argocd-namespace", default=ARGOCD_NAMESPACE)
    parser.add_argument(
        "--via-service",
        help="URL del Service del diagnostico (p.ej. "
        "http://argocd-diagnostician.apps.svc.cluster.local): delega el diagnostico "
        "en el Deployment en vez de ejecutarlo localmente",
    )
    args = parser.parse_args()

    if args.via_service and not args.app:
        parser.error("--via-service requiere --app")

    ensure_kubeconfig()

    if not args.app:
        print(f"[diagnostician] escuchando en 0.0.0.0:{PORT}", flush=True)
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
        return 0

    if args.via_service:
        try:
            report = call_service(args.via_service, args.app)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            print(json.dumps({"application": args.app, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
            return 1
    else:
        try:
            report = diagnose(args.app, args.argocd_namespace)
        except KubectlError as exc:
            print(json.dumps({"application": args.app, "error": str(exc)}, indent=2))
            return 1

    text = json.dumps(report, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
