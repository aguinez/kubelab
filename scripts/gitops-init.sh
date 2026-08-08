#!/usr/bin/env bash
# Inicializa el repositorio de configuración local para ArgoCD y
# despliega los Applications correspondientes.
set -euo pipefail

KIND_CONTEXT="kind-kubelab"
GITOPS_DIR="gitops"
ARGOCD_NS="argocd"
SERVER="https://kubernetes.default.svc"

# Repo de configuración: usamos el repo local del laboratorio
REPO_URL="https://github.com/aguinez/kubelab"
REPO_NAME="kubelab"

mkdir -p "${GITOPS_DIR}/apps"

cat > "${GITOPS_DIR}/apps/${REPO_NAME}.yaml" <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${REPO_NAME}
  namespace: ${ARGOCD_NS}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: ${REPO_URL}
    targetRevision: HEAD
    path: clusters/local
  destination:
    server: ${SERVER}
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
EOF

echo "==> Aplicando Application '${REPO_NAME}'"
kubectl --context "${KIND_CONTEXT}" -n "${ARGOCD_NS}" apply -f "${GITOPS_DIR}/apps/${REPO_NAME}.yaml"
echo "==> Application creada. Sincronizando..."
kubectl --context "${KIND_CONTEXT}" -n "${ARGOCD_NS}" wait --for=condition=Healthy --timeout=120s application/${REPO_NAME} 2>/dev/null || true
