#!/usr/bin/env bash
# Construye la imagen del diagnostico y la carga en el cluster KinD.
# Sin registro de contenedores en el lab, la imagen se construye en local y se
# carga con `kind load docker-image` (+ imagePullPolicy: IfNotPresent).
set -euo pipefail

IMAGE="${IMAGE:-kubelab/argocd-diagnostician:1.0.0}"
KIND_CLUSTER="${KIND_CLUSTER:-kubelab}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build --provenance=false --sbom=false -t "${IMAGE}" "${DIR}"
kind load docker-image --name "${KIND_CLUSTER}" "${IMAGE}"

echo "==> Imagen ${IMAGE} cargada en el cluster ${KIND_CLUSTER}"
