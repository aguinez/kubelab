#!/usr/bin/env bash
# Construye la imagen de n8n (con kubectl y jq) y la carga en el cluster KinD.
# Sin registro de contenedores en el lab, la imagen se construye en local y se
# carga con `kind load docker-image` (+ imagePullPolicy: IfNotPresent).
set -euo pipefail

IMAGE="${IMAGE:-kubelab/n8n:2.45.4}"
KIND_CLUSTER="${KIND_CLUSTER:-kubelab}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Con BuildKit, desactivar provenance/sbom: `kind load` no admite los manifiestos
# de atestacion que genera. El builder legacy no conoce esos flags.
build_args=()
if [ "${DOCKER_BUILDKIT:-0}" = "1" ]; then
  build_args+=(--provenance=false --sbom=false)
fi

docker build "${build_args[@]}" -t "${IMAGE}" "${DIR}"
kind load docker-image --name "${KIND_CLUSTER}" "${IMAGE}"

echo "==> Imagen ${IMAGE} cargada en el cluster ${KIND_CLUSTER}"
