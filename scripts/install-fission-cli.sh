#!/usr/bin/env bash
set -euo pipefail

VERSION="${FISSION_VERSION:-v1.27.0}"

case "$(uname -m)" in
  x86_64|amd64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "Arquitectura no soportada: $(uname -m)" >&2; exit 1 ;;
esac

if command -v fission >/dev/null 2>&1; then
  INSTALLED="$(fission version --client 2>/dev/null | awk '/Version:/{print $2; exit}')"
  if [ "$INSTALLED" = "$VERSION" ]; then
    echo "fission $VERSION ya instalado"
    exit 0
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSLo "$TMP/fission" \
  "https://github.com/fission/fission/releases/download/${VERSION}/fission-${VERSION}-linux-${ARCH}"
sudo install -m 0755 "$TMP/fission" /usr/local/bin/fission

fission version --client
