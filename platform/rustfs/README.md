# RustFS sobre KubeBlocks

Almacenamiento de objetos compatible con S3, gestionado por **KubeBlocks**.

## Estructura

| Fichero | Qué contiene |
|---|---|
| `addon.yaml` | `ComponentDefinition` + `ComponentVersion` del addon RustFS 0.1.0 y los ConfigMaps de plantilla (namespace `kb-system`). Vendorizados desde el chart oficial. |
| `cluster.yaml` | Instancia `Cluster` (1 réplica, PVC de 10Gi) en el namespace `rustfs`. |
| `ingress.yaml` | Ingress + Certificate para la consola y la API S3. |
| `kustomization.yaml` | Agrupa los tres anteriores. |

El operador KubeBlocks se instala aparte (`gitops/apps/kubeblocks.yaml`), junto
con el bundle de CRDs vendorizado en `platform/kubeblocks/crds/`.

## Endpoints

| Host | Puerto | Uso |
|---|---|---|
| `https://rustfs.lab.test` | 9001 | Consola web |
| `https://rustfs-s3.lab.test` | 9000 | API S3 |

## Credenciales

KubeBlocks genera la cuenta `root` en el Secret `rustfs-rustfs-account-root`:

```bash
export RUSTFS_ACCESS_KEY=$(kubectl -n rustfs get secret rustfs-rustfs-account-root -o jsonpath='{.data.username}' | base64 -d)
export RUSTFS_SECRET_KEY=$(kubectl -n rustfs get secret rustfs-rustfs-account-root -o jsonpath='{.data.password}' | base64 -d)
```

## Regenerar el addon vendorizado

Si se actualiza el addon, re-renderizar desde el chart oficial y volver a
aplicar las anotaciones `argocd.argoproj.io/sync-wave: "-2"` y el
`namespace: kb-system` del ConfigMap de scripts:

```bash
helm repo add kubeblocks-addons https://jihulab.com/api/v4/projects/150246/packages/helm/stable
helm repo update
helm template rustfs-addon kubeblocks-addons/rustfs --version 0.1.0 -n kb-system \
  --set image.registry=docker.io \
  --set image.repository=rustfs/rustfs \
  > platform/rustfs/addon.yaml
```

## Escalado

El ComponentDefinition admite de 1 a 32 réplicas, pero un pool de erasure coding
no soporta *scale-in* (KubeBlocks lo rechaza). Para pasar a modo distribuido
sube `replicas` a un número soportado (p. ej. 4).
