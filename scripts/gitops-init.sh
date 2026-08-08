#!/usr/bin/env bash
# Registra el repo de GitOps en ArgoCD y aplica el Application raíz.
# Requisito: el repo ya debe existir en GitHub y tener los manifests en clusters/local.
set -euo pipefail

KIND_CONTEXT="kind-kubelab"
ARGOCD_NS="argocd"
ARGOCD_HOST="argocd.lab.test"
REPO_URL="https://github.com/aguinez/kubelab"
APP_FILE="gitops/apps/kubelab.yaml"

# Obtener token de sesión de ArgoCD (login inicial admin)
PASS=$(kubectl --context "${KIND_CONTEXT}" -n "${ARGOCD_NS}" get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)
TOKEN=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"${PASS}\"}" \
  "https://${ARGOCD_HOST}/api/v1/session" | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")

echo "==> Registrando repo ${REPO_URL}"
curl -sk -X POST -H "Content-Type: application/json" -H "Authorization: Bearer ${TOKEN}" \
  -d "{\"type\":\"git\",\"name\":\"kubelab\",\"repo\":\"${REPO_URL}\"}" \
  "https://${ARGOCD_HOST}/api/v1/repositories" >/dev/null || true

echo "==> Aplicando Application 'kubelab'"
kubectl --context "${KIND_CONTEXT}" -n "${ARGOCD_NS}" apply -f "${APP_FILE}"

echo "==> Sincronizando..."
kubectl --context "${KIND_CONTEXT}" -n "${ARGOCD_NS}" wait --for=jsonpath='{.status.health.status}'=Healthy --timeout=120s application/kubelab 2>/dev/null || true
