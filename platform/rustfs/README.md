# RustFS (instalación tradicional)

Almacenamiento de objetos compatible con S3, desplegado como Deployment normal
(sin KubeBlocks).

## Componentes

| Fichero | Contenido |
|---|---|
| `pvc.yaml` | PVC `rustfs-data` (10Gi, `standard`). |
| `deployment.yaml` | Deployment `rustfs` (imagen `rustfs/rustfs:1.0.4`). |
| `service.yaml` | Service con puertos `api` (9000) y `console` (9001). |
| `ingress.yaml` | Certificate + Ingress para consola y API. |

## Credenciales

No se guardan en Git. El Deployment lee el Secret `rustfs-credentials`
(claves `RUSTFS_ACCESS_KEY` y `RUSTFS_SECRET_KEY`) del namespace `rustfs`.
Hay que crearlo una vez:

```bash
kubectl -n rustfs create secret generic rustfs-credentials \
  --from-literal=RUSTFS_ACCESS_KEY=rustfsadmin \
  --from-literal=RUSTFS_SECRET_KEY=rustfsadmin
```

> Son las credenciales por defecto documentadas por RustFS y solo válidas para
> este laboratorio. Cámbialas antes de exponer el servicio fuera del lab.

## Endpoints

| Host | Puerto | Uso |
|---|---|---|
| `https://rustfs.lab.test` | 9001 | Consola (redirige a `/rustfs/console/`) y API S3 |
| `https://rustfs-s3.lab.test` | 9000 | API S3 dedicada para apps |

La consola y el S3 comparten el host `rustfs.lab.test` a propósito: la UI de
RustFS no soporta bien consola y endpoint en dominios distintos.

## Acceso directo (si el Ingress diera problemas)

La consola de RustFS tiene bugs conocidos detrás de reverse proxy. Si la UI no
carga bien por el dominio, usa acceso directo:

```bash
kubectl -n rustfs port-forward svc/rustfs 9000:9000 9001:9001
```

Abre `http://localhost:9001/rustfs/console/` y entra por **Key Login**.
