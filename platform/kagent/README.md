# kagent (plataforma)

Plano de control de agentes de IA sobre Kubernetes, instalado con el chart
oficial **0.10.6** (`oci://ghcr.io/kagent-dev/kagent/helm`).

## Estructura

| Ruta | Contenido |
|---|---|
| `platform/kagent/values.yaml` | Valores base (sin secretos). |
| `platform/kagent/ingress/` | Ingress + Certificate de la UI (`kagent.lab.test`). |
| `clusters/local/infra-applications/kagent/values-kind.yaml` | Overrides de KinD (recursos, PostgreSQL, kmcp off). |
| `apps/kagent/team-a/` | CRD `Agent/team-a-agent`. |
| `gitops/apps/kagent-crds.yaml` | Application de CRDs (prune: false). |
| `gitops/apps/kagent.yaml` | Application del chart + ingress. |
| `gitops/apps/kagent-team-a.yaml` | Application del agente. |

## Dependencias

- ArgoCD con soporte Helm OCI (v3.x lo trae).
- cert-manager (`ClusterIssuer/lab-issuer`) e ingress-nginx.
- StorageClass `standard` para el PostgreSQL bundled.

## Secret del LLM (fuera de Git)

El chart espera el Secret `kagent-openai` con la clave `OPENAI_API_KEY`:

```bash
kubectl -n kagent create secret generic kagent-openai \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
```

Sin la clave el controlador y la UI levantan, pero los agentes no responden.

## Acceso

- UI: `https://kagent.lab.test` (confiar en la CA interna `lab-root-ca.crt`).
- Fallback: `kubectl -n kagent port-forward svc/kagent-ui 8080:8080` y
  `http://localhost:8080`.

## Verificación

```bash
kubectl get crd | grep kagent.dev
kubectl -n kagent get pods
kubectl -n kagent get agents,modelconfigs
kubectl -n kagent get pvc
```
