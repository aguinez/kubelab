#!/usr/bin/env bash
set -euo pipefail

KIND_CLUSTER="kubelab"

echo "==> Verificando prerequisites"
for cmd in docker kind kubectl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: $cmd no está instalado" >&2
    exit 1
  fi
done

docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon no está corriendo" >&2; exit 1; }

echo "==> Creando cluster KinD '${KIND_CLUSTER}' (3 nodos)"
if kind get clusters 2>/dev/null | grep -qx "${KIND_CLUSTER}"; then
  echo "El cluster '${KIND_CLUSTER}' ya existe, saltando creación"
else
  kind create cluster --config "$(dirname "$0")/cluster.yaml"
fi

echo "==> Cluster listo:"
kubectl cluster-info --context "kind-${KIND_CLUSTER}" 2>/dev/null | head -2
