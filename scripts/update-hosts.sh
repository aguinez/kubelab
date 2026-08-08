#!/usr/bin/env bash
# Sincroniza los hostnames de los Ingress del cluster hacia /etc/hosts
# (Linux/WSL) y hacia el hosts de Windows (via powershell.exe).
# Los puertos de KinD se reenvían a localhost de Windows, por eso se usa
# 127.0.0.1.
set -euo pipefail

KIND_CONTEXT="kind-kubelab"
LAB_MARKER="# BEGIN kubelab-lab"
LAB_MARKER_END="# END kubelab-lab"

if ! kubectl --context "${KIND_CONTEXT}" get nodes >/dev/null 2>&1; then
  echo "ERROR: cluster ${KIND_CONTEXT} no accesible" >&2
  exit 1
fi

# Extraer todos los hostnames de los Ingress (también los de TLS)
mapfile -t HOSTS < <(kubectl --context "${KIND_CONTEXT}" get ingress -A -o json \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
hosts=set()
for i in d.get('items',[]):
    for r in i.get('spec',{}).get('rules',[]):
        if r.get('host'): hosts.add(r['host'])
    for t in i.get('spec',{}).get('tls',[]):
        for h in t.get('hosts',[]): hosts.add(h)
print('\n'.join(sorted(hosts)))
")

if [ ${#HOSTS[@]} -eq 0 ]; then
  echo "No se encontraron Ingress con hostnames."
  exit 0
fi

BLOCK=""
for h in "${HOSTS[@]}"; do
  BLOCK+="127.0.0.1 ${h}"$'\n'
done

# --- /etc/hosts (Linux) ---
if grep -q "${LAB_MARKER}" /etc/hosts 2>/dev/null; then
  sudo sed -i "/${LAB_MARKER}/,/${LAB_MARKER_END}/c\\
${LAB_MARKER}\\
${BLOCK}${LAB_MARKER_END}" /etc/hosts
else
  echo "${LAB_MARKER}" | sudo tee -a /etc/hosts >/dev/null
  echo "${BLOCK}${LAB_MARKER_END}" | sudo tee -a /etc/hosts >/dev/null
fi
echo "==> /etc/hosts (Linux):"
grep -A100 "${LAB_MARKER}" /etc/hosts | head -10

# --- hosts de Windows ---
if command -v powershell.exe >/dev/null 2>&1; then
  WINDOWS_HOSTS="/mnt/c/Windows/System32/drivers/etc/hosts"
  if [ -f "${WINDOWS_HOSTS}" ]; then
    # Construir el bloque y reemplazar vía powershell (necesita admin)
    WBLOCK=$(printf '%s\n' "${BLOCK}" | sed 's/\\/\\\\/g')
    powershell.exe -NoProfile -Command "
      \$p = 'C:\Windows\System32\drivers\etc\hosts'
      \$content = Get-Content \$p -Raw
      \$marker = '${LAB_MARKER}'
      \$markerEnd = '${LAB_MARKER_END}'
      \$block = @'
${LAB_MARKER}
${BLOCK}${LAB_MARKER_END}
'@
      if (\$content -match [regex]::Escape(\$marker)) {
        \$content = [regex]::Replace(\$content, [regex]::Escape(\$marker) + '.*?' + [regex]::Escape(\$markerEnd), \$block, 'Singleline')
      } else {
        \$content += [Environment]::NewLine + \$block
      }
      Set-Content -Path \$p -Value \$content -NoNewline
      Write-Host '==> hosts de Windows actualizado'
      Get-Content \$p | Select-String '${LAB_MARKER}' -Context 0,5 | ForEach-Object { \$_.Line }
    " 2>&1 || echo "  (aviso: no se pudo escribir el hosts de Windows — ejecuta con permisos de admin o hazlo manual)"
  else
    echo "  (no se encontró /mnt/c/Windows/System32/drivers/etc/hosts)"
  fi
else
  echo "  (powershell.exe no disponible)"
fi

echo "==> Listo. Hosts registrados: ${HOSTS[*]}"
