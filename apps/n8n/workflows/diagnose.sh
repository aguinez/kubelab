#!/bin/sh
# Diagnostico de una ArgoCD Application usando kubectl.
#
# Uso: diagnose.sh <application> [namespace-argocd  (default: argocd)]
#
# Recoge el estado de la Application, la lista de sus recursos y, para cada uno,
# `describe` y (si es un workload) los logs de sus pods. Tambien lista los
# eventos recientes. Solo operaciones de lectura.
#
# ArgoCD (>= v3) no siempre rellena la salud por recurso en status.resources, asi
# que no se filtra por salud: se vuelca el crudo y el paso LLM hace el analisis.
set -u

APP="${1:-}"
NS="${2:-${ARGOCD_NAMESPACE:-argocd}}"

if [ -z "$APP" ]; then
  echo "falta el nombre de la Application"
  exit 1
fi

# kubectl no usa la configuracion in-cluster por si solo: se construye un
# kubeconfig a partir del ServiceAccount montado en el pod.
if [ -z "${KUBECONFIG:-}" ] && [ -n "${KUBERNETES_SERVICE_HOST:-}" ]; then
  SA=/var/run/secrets/kubernetes.io/serviceaccount
  KUBECONFIG=/tmp/kubeconfig
  cat > "$KUBECONFIG" <<EOF
apiVersion: v1
kind: Config
clusters:
- name: in-cluster
  cluster:
    certificate-authority: $SA/ca.crt
    server: https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT
users:
- name: sa
  user:
    tokenFile: $SA/token
contexts:
- name: in-cluster
  context:
    cluster: in-cluster
    user: sa
current-context: in-cluster
EOF
  export KUBECONFIG
fi

echo "### Application: $APP (namespace $NS)"
kubectl -n "$NS" get application "$APP" -o json 2>/dev/null \
  | jq -c '{health: .status.health.status, sync: .status.sync.status,
            resources: [.status.resources[]? | {kind, name, namespace}]}' 2>/dev/null \
  || echo "(no se pudo leer la Application)"

echo
echo "### Recursos [kind  namespace  name  sync]"
kubectl -n "$NS" get application "$APP" -o json 2>/dev/null | jq -r '
  .status.resources[]?
  | [.kind, (.namespace // "-"), .name, (.status // "?")] | @tsv' 2>/dev/null

echo
echo "### Detalle por recurso (describe + logs)"
kubectl -n "$NS" get application "$APP" -o json 2>/dev/null | jq -r '
  .status.resources[]? | [.kind, (.namespace // ""), .name] | @tsv' 2>/dev/null \
| while IFS="$(printf '\t')" read -r KIND RNS NAME; do
    [ -z "${KIND:-}" ] && continue
    if [ -n "$RNS" ]; then NSARG="-n $RNS"; else NSARG=""; fi
    echo
    echo "--- $KIND/$NAME (ns=${RNS:-cluster}) ---"
    kubectl $NSARG describe "$KIND" "$NAME" 2>&1 | tail -n 18
    case "$KIND" in
      Pod)
        echo "  [logs $NAME]"
        kubectl $NSARG logs "$NAME" --tail=40 --all-containers 2>&1 | tail -n 40
        kubectl $NSARG logs "$NAME" --tail=20 --all-containers --previous 2>&1 | tail -n 20
        ;;
      Deployment|ReplicaSet|StatefulSet|DaemonSet|Job)
        SEL=$(kubectl $NSARG get "$KIND" "$NAME" -o jsonpath='{.spec.selector.matchLabels}' 2>/dev/null \
              | jq -r 'to_entries | map("\(.key)=\(.value)") | join(",")' 2>/dev/null)
        if [ -n "$SEL" ]; then
          for P in $(kubectl $NSARG get pods -l "$SEL" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null); do
            echo "  [logs $P]"
            kubectl $NSARG logs "$P" --tail=40 --all-containers 2>&1 | tail -n 40
          done
        fi
        ;;
    esac
  done

echo
echo "### Eventos recientes (namespace $NS)"
kubectl -n "$NS" get events --sort-by=.lastTimestamp 2>&1 | tail -n 15
