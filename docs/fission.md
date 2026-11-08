# Fission + función Python con Warm Pool

Instalación declarativa de [Fission](https://fission.io) en el clúster KIND del
laboratorio y despliegue de una función `hello` en Python servida desde el
**pool de pods precalentados** (`poolmgr`).

## Versiones

| Componente | Versión |
|---|---|
| Fission (chart `fission-all`, servidor y CLI) | **v1.27.0** |
| Entorno Python | `ghcr.io/fission/python-env:1.35.0` |
| Kubernetes (real) | v1.37.0 |

> El chart de Fission v1.27.0 exige Kubernetes **≥ 1.32** (`kubeVersion`).
> `docs/cluster-creation-notes.md` documenta v1.31.0, pero el clúster actual ya
> corre **v1.37.0** (`kubectl version`), así que no fue necesario recrearlo.
> Si algún día se vuelve a un nodo < 1.32, `helm install` fallará: habría que
> fijar `image: kindest/node:v1.32.x` en `bootstrap/kind/cluster.yaml` o bajar
> a Fission v1.24.0 (mínimo 1.28).

## Estado deseado en Git (ArgoCD)

Tres Applications dentro del app-of-apps (`gitops/apps/`):

| Application | Onda | Origen | Qué crea |
|---|---|---|---|
| `fission-crds` | -2 | `platform/fission/crds` | 9 CRDs de `fission.io/v1` vendoreados desde v1.27.0 |
| `fission` | -1 | chart `fission-all` 1.27.0 + `platform/fission/values.yaml` + `platform/fission/ingress` | plano de control, Ingress y Certificate |
| `fission-functions` | 0 | `apps/fission` | `Environment`, `Package`, `Function`, `HTTPTrigger` |

Notas:

- Los CRDs se aplican con **ServerSideApply** porque `fission.io_environments.yaml`
  (~1.4 MB) supera el límite de 256 KB de la anotación `last-applied-configuration`.
- `prune: false` en `fission-crds` a propósito: borrar un CRD elimina en cascada
  todos sus CRs.
- El namespace `fission` está declarado en Git
  (`clusters/local/infra-applications/namespaces/namespaces.yaml`) con su
  justificación. Las **funciones** viven en `apps`
  (`defaultNamespace: apps`), no en `fission`.
- `platform/fission/values.yaml` es la única fuente de valores Helm (la
  Application lo consume como *multi-source* con `ref: values`).

## Valores relevantes (`platform/fission/values.yaml`)

```yaml
serviceType: NodePort
routerServiceType: NodePort
imageTag: v1.27.0
defaultNamespace: apps
createNamespace: false
analytics: false
mqt_keda:
  enabled: false          # no usamos triggers de colas KEDA
persistence:
  enabled: false          # emptyDir; el código viaja como literal en el Package
```

Requests **mínimos** (es un laboratorio en un solo equipo). Los limits dejan
margen para picos sin reservar recursos:

| Componente | requests | limits |
|---|---|---|
| executor | 10m / 32Mi | 500m / 256Mi |
| router | 10m / 32Mi | 300m / 192Mi |
| webhook, buildermgr, kubewatcher, timer, storagesvc | 10m / 32Mi | 200m / 128Mi |
| pods del pool Python | 10m / 32Mi | 200m / 192Mi |

`serviceType`/`routerServiceType: NodePort` cumplen la restricción de no usar
`LoadBalancer` en KIND. El router queda además accesible por HTTPS vía Ingress
(`fission.lab.test`).

## Función declarativa

```yaml
# Environment: version 3 habilita poolsize
spec:
  version: 3
  poolsize: 2
  runtime:
    image: ghcr.io/fission/python-env:1.35.0
  resources:
    requests: { cpu: 10m, memory: 32Mi }
    limits:   { cpu: 200m, memory: 192Mi }
```

```python
# apps/fission/hello.py  ->  Package.spec.deployment.literal (base64)
def main():
    return "Hello, world!\n"
```

`Package` usa `deployment.type: literal` con el código en **base64** (el campo es
`[]byte`). Se regenera con `make fission-pkg`; el objetivo falla si no hay
exactamente un `literal:` en el manifiesto.

`HTTPTrigger` (`/hello`, GET) es necesario para que el router de v1.27 publique
la función en el listener público.

## Instalación del CLI

```bash
make fission-cli     # o: bash scripts/install-fission-cli.sh
```

El script detecta `amd64`/`arm64`, fija v1.27.0 y, si `/usr/local/bin` no es
escribible, instala en `~/.local/bin` (sin `sudo`). Añade ese directorio al
`PATH` si hace falta.

## Verificación

```bash
$ fission check
fission-services
--------------------
√ executor is running fine
√ router is running fine
√ storagesvc is running fine
√ webhook is running fine

fission-version
--------------------
√ fission is up-to-date

oci-delivery
--------------------
√ package registry configuration is consistent
√ image-volume delivery is supported by this cluster
```

```bash
$ fission function list --namespace apps
NAME  ENV    EXECUTORTYPE MINSCALE MAXSCALE ... READY  NAMESPACE
hello python poolmgr      0        0        ... <none> apps
```

### Warm pool

El ejecutor por defecto es `poolmgr` y mantiene `poolsize: 2` pods genéricos:

```bash
$ kubectl -n apps get pods -l environmentName=python
NAME                                         READY   STATUS
poolmgr-python-apps-66379-675dc854ff-42wqn   2/2     Running
poolmgr-python-apps-66379-675dc854ff-ffq8h   2/2     Running
```

Tras la primera invocación, el pod especializado queda relabelado
(`functionName=hello`, `fission.io/served=true`, `managed=false`) y el ejecutor
lo reutiliza:

```text
choosing pod from pool ... pod=poolmgr-python-apps-66379-675dc854ff-ffq8h
specializing pod ... function=hello
specialized pod ... function=hello
added function service ... serviceHost=10.244.2.16:8888
```

El pod especializado **sale del pool**: se le quita el `ownerReferences` y la
label `managed=true`, así que el ReplicaSet del pool crea otro pod genérico y
mantiene `poolsize` pods calientes. Por eso con 1 función activa se ven 3 pods
(2 warm + 1 especializado).

La función declara `spec.idletimeout: 60`, de modo que si no recibe tráfico
durante un minuto el *idle reaper* del executor borra el pod especializado y
vuelve a quedarse solo el pool precalentado.

### Invocación y latencia (Ingress + TLS)

```bash
curl --resolve fission.lab.test:443:127.0.0.1 \
     --cacert <CA real del ClusterIssuer lab-issuer> \
     https://fission.lab.test/hello
```

Resultado medido (`time_total`):

| Llamada | Resultado | Latencia |
|---|---|---|
| 1 (especialización) | `Hello, world!` | **74.9 ms** |
| 2 | `Hello, world!` | 8.1 ms |
| 3 | `Hello, world!` | 6.4 ms |
| 4 | `Hello, world!` | 6.0 ms |
| 5 | `Hello, world!` | 5.4 ms |

La primera llamada paga la especialización (≈75 ms, sin arranque de contenedor);
las siguientes son de un solo dígito de milisegundos, lo que confirma que el pod
del warm pool está caliente y reutilizándose.

Para reproducir el cold start desde el pool:

```bash
kubectl -n apps delete pod -l functionName=hello
curl ... https://fission.lab.test/hello   # ~75 ms otra vez
```

## Limitaciones conocidas

- **`fission function test` devuelve 404 con v1.27.0.** El CLI hace
  port-forward al *listener público* (8888) y llama a
  `/fission-function/<ns>/<fn>`, ruta que el router ya solo sirve en el listener
  interno (separación por GHSA-3g33-6vg6-27m8). Verificación equivalente y
  funcional: el `HTTPTrigger` + Ingress de arriba. `fission check`,
  `fission env list` y `fission function list` funcionan con normalidad.
- **`lab-root-ca.crt` del repo no corresponde al CA actual.** El `ClusterIssuer
  lab-issuer` usa el secret `lab-root-ca-tls` de `cert-manager`; el certificado
  servido en `fission.lab.test` valida contra ese CA, no contra el fichero
  versionado (tiene otra clave). Conviene regenerar/actualizar ese fichero.
- **Kyverno en modo Audit**: los `Deployment` que crea el chart no llevan las
  labels `app`/`owner`/`environment` (el chart no permite inyectarlas), así que
  `require-labels` reportará violaciones. No bloquea.
- `internalAuth` queda habilitado (default del chart). El listener interno del
  router (8889) exige HMAC y no está expuesto por el Ingress.

## Comandos útiles

```bash
kubectl -n argocd get applications | grep fission   # estado GitOps
kubectl -n fission get pods                         # plano de control
kubectl -n apps get pods -l environmentName=python  # warm pool
make fission-verify                                 # fission check + listados
```
