# Bitácora de despliegue — Etapa 1

> Documento vivo: cada fase del despliegue se registra aquí como lo haría una
> persona: qué hice, qué asumí sin comprobar, qué errores cometí y qué aprendí.

Fecha inicio: 2026-08-07
Cluster: `kubelab` (KinD, 3 nodos, K8s v1.31.0)

---

## Fase 0 — Preparación

### Qué hice
- Revisé el plan (`PLAN.MD`) y las herramientas instaladas (docker, kind,
  kubectl, helm; faltaba kustomize standalone).
- Inicialicé git local y conecté el remoto `github.com/aguinez/kubelab`.

### Errores y cosas que asumí sin comprobar
- **Asumí que el directorio del proyecto era escribible.** No lo comprobé al
  empezar: era propiedad de `root` y `git init` falló con `Permission denied`.
  Tuve que detenerme y pedir al usuario que corrigiera los permisos.
  *Aprendizaje: `ls -ld` antes de empezar a escribir archivos. Siempre.*
- **Asumí que el contexto de kubectl era el del lab.** El contexto por defecto
  del kubeconfig apuntaba a un cluster viejo (`transfer-platform`) que estaba
  caído. Durante un buen rato vi errores `connection reset by peer` y pensé que
  el cluster nuevo fallaba. No era así: era el cluster ajeno al que kubectl
  seguía apuntando.
  *Aprendizaje: comprobar `kubectl config current-context` antes de diagnosticar
  cualquier error de conexión.*

---

## Fase 1 — Creación del cluster KinD

### Intento 1: timeout del comando
- **Error:** ejecuté `kind create cluster` con un timeout de 3 minutos. Se
  cortó en `Starting control-plane`. Los contenedores quedaron "Up" pero el
  cluster no terminó: sin contexto en kubeconfig, API server sin responder.
- **Causa:** asumí que la creación de un cluster de 3 nodos cabía en 3 min.
  No había creado nunca uno así y no lo verifiqué. Entre descarga de imagen,
  kubeadm init, CNI y unión de workers, necesita más tiempo.
- **Limpieza:** borré solo el cluster `kubelab` (sin tocar `transfer-platform`).
- **Aprendizaje:** timeouts amplios (7-10 min) para `kind create`. Y si un
  comando se corta, verificar el estado real (contenedores, kubeconfig) antes
  de asumir que falló o funcionó.

### Intento 2: kubelet no saludable
- **Error:** el `cluster.yaml` llevaba un `kubeadmConfigPatch` que añadía la
  label `node-role.kubernetes.io/control-plane` al kubelet del control-plane.
  kubeadm falló con `The kubelet is not healthy after 4m`.
- **Lo que asumí sin comprobar:** que ese patch era útil o al menos inocuo.
  No lo era: rompía el arranque del kubelet. La label ya la pone KinD solo.
- **Diagnóstico:** aislé la variable. Creé un cluster de prueba con la misma
  topología (3 nodos) pero sin patches → arrancó perfecto. Eso confirmó la
  causa.
- **Aprendizaje:**
  - No añadir configuración que no aporte valor real. Menos es más.
  - Ante un fallo de arranque, aislar variables: un cluster mínimo que funcione
    es el mejor test.
  - Leer los logs del nodo (kubelet) en lugar de adivinar.

### Resultado
- 3 nodos `Ready` (control-plane + 2 workers), API server sano (`/readyz` → ok),
  puertos 80/443 del host libres y mapeados al control-plane.

---

## Fase 2 — Componentes base

### Namespaces
- Creados `cert-manager`, `traefik`, `kyverno`, `argocd` vía kustomize. Sin
  incidencias.

### cert-manager + PKI interna
- Instalé cert-manager v1.16.2 (manifiesto oficial) → 3 pods Running.
- Apliqué la CA interna (`lab-root-ca`, self-signed) y el `ClusterIssuer`
  (`lab-issuer`).
- **Error de juicio:** al crear el ClusterIssuer, `kubectl get clusterissuers`
  lo mostraba `False`. Me alarmé y me puse a inspeccionar con `describe`.
  Resultado: unos segundos después estaba `True` (`KeyPairVerified`).
  *Aprendizaje: los controllers necesitan tiempo para poblar el status; esperar
  y re-comprobar antes de diagnosticar un "fallo".*
- Decisión: la CA emite con ECDSA y 10 años de validez; los certificados
  emitidos se resuelven bajo `*.lab.test`.

---

## Fase 3 — Traefik (en curso)

### Primer apply: CRD faltante
- **Error:** `kubectl apply -k platform/traefik` creó SA, RBAC, Secret, Service,
  Deployment, Certificate e Ingress, pero falló en el `Middleware`:
  `no matches for kind "Middleware" in version "traefik.io/v1alpha1"`.
- **Lo que asumí sin comprobar:** que el kustomization incluía todo lo
  necesario (incluidas las CRDs). No: las CRDs de Traefik viven en un manifest
  aparte que hay que instalar antes.
- **Solución:** apliqué las CRDs desde el repo oficial de Traefik (v3.1.7) y
  reintenté.
- **Aprendizaje:** los CRDs de un operador/controller no se instalan solos con
  el kustomization del recurso; son un prerequisito explícito. Verificar CRDs
  (`kubectl get crd | grep traefik`) antes de aplicar recursos que las usan.

### Pendiente
- Reaplicar `-k platform/traefik` completo, esperar rollout y validar el
  dashboard con TLS.

---

## Fase 3 — Ingress controller (Traefik → ingress-nginx)

### Traefik: demasiados problemas con el manifest manual
- **Error:** el `Middleware` requería CRDs que no instalé → `no matches for kind`.
- **Error:** RBAC incompleto (faltaban `nodes`, `endpointslices`, CRDs `traefik.io`).
- **Error:** readiness probe apuntaba a `/ping` sin habilitar `--ping`.
- **Error:** `LoadBalancer` en KinD no recibe tráfico (no hay LB nativo) → tuve que
  usar hostPort en el control-plane + toleration.
- **Error:** el basic-auth fallaba: el hash `{SHA}` no es aceptado; luego bcrypt en
  imagen con musl tampoco. El dashboard del chart oficial requería exponer el puerto
  `traefik` (8080) en el Service.
- **Lo que asumí sin comprobar:** que las CRDs se instalaban solas, que el RBAC del
  manifest era suficiente, que LoadBalancer funcionaba en KinD, que el hash de auth
  funcionaría en la imagen. **Todo estaba mal.**
- **Decisión final:** abandonar Traefik. El chart oficial funcionaba pero la curva de
  configuración para el dashboard no valía la pena para el objetivo del lab.

### Cambio a ingress-nginx (decisión acertada)
- **Error:** instalé el chart de Helm de ingress-nginx con hostNetwork, y el pod
  quedaba 0/1 (deadlock de hostPort en rollout).
- **Error (clave):** el basic-auth con hash `$apr1$` (generado con `htpasswd`)
  fallaba siempre con `password mismatch`. **Causa raíz:** la imagen del controller
  es Alpine (musl), y `crypt()` de musl NO soporta hashes `$apr1$` (glibc), ni `$2y$`
  (bcrypt). Solo `$1$` (MD5 estándar), `$5$`, `$6$`. Generé hash con
  `openssl passwd -1` y la auth funcionó.
- **Error:** al recrear el secret con `kubectl apply` sobre uno creado con
  `--from-file`, el archivo montado quedó con **dos hashes concatenados** (merge de
  `stringData` con el `data` existente). El controller cachea el archivo y hay que
  reiniciar limpio (scale down/up) tras tocar secrets.
- **Aprendizaje:** con ingress-nginx hay que seguir el **manifiesto oficial para
  KinD** (`deploy/static/provider/kind/deploy.yaml`), NO el chart de Helm, ni
  manifest hechos a mano. Ese manifiesto ya trae hostPort 80/443, tolerations y
  RBAC correctos. Solo hay que añadir el `nodeSelector` para fijarlo al nodo que
  publica los puertos (el control-plane).

### Resultado validado
- Controller corriendo en `kubelab-control-plane` (puertos 80/443 del host).
- App demo nginx con Ingress + TLS interno:
  - `https://traefik.lab.test` → **200** (certificado firmado por `lab-root-ca`)
  - `http://traefik.lab.test` → **308** (redirect a HTTPS)
- nginx no tiene dashboard web: se usa la app demo como página de validación.

---

## Fase 4 — Kyverno

- **Error:** v1.12.5 (que estaba en el Makefile original) fallaba al instalar:
  los CRDs superaban el límite de anotaciones del API server
  (`metadata.annotations: Too long: must have at most 262144 bytes`).
- **Solución:** usar la versión actual v1.18.2 (chart helm 3.8.2). CRDs OK.
- Resultado: 4 controladores Running + 5 ClusterPolicies en modo Audit, con
  policyreports generados (PASS/FAIL por workload).

## Fase 5 — ArgoCD + GitOps

- **Error:** puse `server.config."server.insecure"=true` en el chart, pero el
  valor correcto es `server.extraArgs[0]=--insecure`. Sin él, la UI redirigía
  en bucle (307). Lo corregí y la UI quedó 200.
- **Aprendizaje:** leer los values del chart (`helm show values`) antes de
  `--set`; los nombres de parámetros no se adivinan.
- GitOps: registré el repo `aguinez/kubelab` en ArgoCD via API, creé la
  Application raíz (`clusters/local`) con sync automático → **Synced/Healthy**.
- Commit + push inicial del repo al remoto.

---

## Fase 6 — DNS interno (CoreDNS expuesto)

- **Objetivo:** que Windows/WSL resuelva los `*.lab.test` de los Ingress.
- **Error:** puse el bloque `lab.test` como subdirectiva dentro de `.:53`
  (`Unknown directive 'lab.test'`). CoreDNS exige un **server block separado**
  (`lab.test:53 { ... }`).
- **Error:** el plugin `hosts` no soporta wildcard `*.lab.test` como subdominios
  (`no next plugin found`). La solución es el plugin **`template`**:
  ```
  lab.test:53 {
      errors
      log
      template IN A {
          match ^.*\.lab\.test\.$
          answer "{{ .Name }} 60 IN A 127.0.0.1"
      }
  }
  ```
- **Error:** el NodePort UDP 30535 no era alcanzable desde WSL (kind solo expone
  los `extraPortMappings` del cluster.yaml). Hubo que **recrear el cluster**
  añadiendo el mapeo 30535 TCP/UDP.
- **Error:** usé `nodeLabels` en el cluster.yaml; en kind v0.24 el campo es
  `labels`. El `kind create` falló con `field nodeLabels not found`.
- **Aprendizaje:** CoreDNS necesita un server block por zona; el plugin
  `template` es el estándar para wildcards; los puertos de kind se exponen solo
  vía extraPortMappings (no sirven los NodePort arbitrarios desde WSL).
- Resultado: `dig @127.0.0.1 -p 30535 *.lab.test` → `127.0.0.1` (NOERROR).
- Nota: tras recrear el cluster hubo que reaplicar toda la plataforma
  (cert-manager, ingress-nginx, kyverno, argocd, gitops) — verificado todo OK.

---

## Fase — Notificaciones de ArgoCD (app que falla + webhook)

Fecha: 2026-10-23

### Objetivo
Siguiendo `task_notification.MD`: (1) una app que falle tras N segundos (default
30), (2) un webhook que reciba e imprima el nombre de la app con problemas que
envía el notifications controller de ArgoCD, y (3) la configuración de las
notificaciones en `platform/argocd`.

### Qué hice
- `apps/app_error_test_notification/`: `app.py` (servidor HTTP que hace
  `os._exit(1)` pasados `FAIL_AFTER_SECONDS`), Dockerfile, Deployment y Service.
- `apps/webhook/`: `webhook.py` (parsea el payload JSON e imprime el nombre de la
  app), Dockerfile, Deployment y Service.
- `platform/argocd/notifications/argocd-notifications-cm.yaml`: ConfigMap con
  `service.webhook.kubelab`, `template.app-problem`, `trigger.on-app-problem` y la
  `subscriptions` global.
- `gitops/apps/`: ArgoCD Applications para las dos apps y para el ConfigMap.

### Errores y cosas que asumí sin comprobar
- **Las imágenes `ghcr.io/aguinez/...` no existían.** Asumí que había registro/CI;
  no hay. El pod quedaba en `ImagePullBackOff`. Solución: construir en local y
  cargar con `kind load docker-image`, usando nombres locales
  (`kubelab/app-error-test:1.0.0`) y `imagePullPolicy: IfNotPresent`.
- **El builder de Docker Desktop añade attestations (manifest lists).** El primer
  build generó un manifest list con provenance; en KinD el kubelet puede no
  resolver la plataforma. Lo resolví con `--provenance=false --sbom=false`.
- **`/tmp` del nodo KinD es tmpfs.** Un `docker cp` a `/tmp` "tenía éxito" pero el
  archivo no aparecía dentro del contenedor (quedaba oculto por el tmpfs). Hay que
  copiar a una ruta del overlay (p.ej. `/root`).
- **Asumí que el notifications controller estaba instalado.** No lo estaba: el
  chart `argo-cd` trae `notifications.enabled=false` por defecto. Lo habilité vía
  Helm (`notifications.enabled=true`) y puse `notifications.cm.create=false` para
  que el ConfigMap sea propiedad del repo y no del chart.
- **Asumí que ArgoCD marca Degraded un Deployment que crashea.** No: ArgoCD solo
  marca Degraded cuando aparece la condición `ProgressDeadlineExceeded`. Mientras
  el pod alcanza a estar Ready una vez, el rollout "completa" y la app se queda
  alternando `Healthy`/`Progressing`.
- **Error de validación:** `progressDeadlineSeconds: 30` con
  `minReadySeconds: 60` es inválido (`must be greater than minReadySeconds`). El
  sync de ArgoCD falló con `SyncError` hasta corregirlo.
- **Operé el cluster desde dentro del nodo** (`docker exec kubelab-control-plane
  kubectl ...`): desde WSL el API server en `127.0.0.1:42527` reseteaba la conexión
  TLS. No era el cluster (dentro del nodo respondía perfecto).

### Cómo queda funcionando
- El pod vive 30s y muere; con `minReadySeconds: 45` (mayor que la vida del pod)
  el ReplicaSet nunca queda "available" → `progressDeadlineSeconds: 60` →
  `ProgressDeadlineExceeded` → ArgoCD lo reporta **Degraded** (estable).
- `trigger.on-app-problem` matchea `health == 'Degraded'` y envía al webhook
  `kubelab` (`http://webhook.apps.svc.cluster.local`).
- Verificado en logs del webhook:
  `[webhook] application with problems: app-error-test`.

### Construir y cargar las imágenes (repetible)
```bash
docker build --provenance=false --sbom=false -t kubelab/app-error-test:1.0.0 apps/app_error_test_notification
docker build --provenance=false --sbom=false -t kubelab/webhook:1.0.0 apps/webhook
kind load docker-image --name kubelab kubelab/app-error-test:1.0.0 kubelab/webhook:1.0.0
```

---

## Fase — Canalización de diagnóstico (Argo Workflows)

Fecha: 2026-10-24

### Objetivo
Siguiendo `task_notification_increment_1.MD`: dejar de solo escribir el log en el
webhook y hacer que una notificación de ArgoCD **levante una canalización de Argo
Workflows**. El primer paso recibe el nombre de la Application degradada, revisa
los objetos que la componen y recolecta evidencia con kubectl (`get`, `describe`,
`logs`, eventos); reduce esa evidencia a firmas únicas (para no acumular el mismo
error repetido) y prepara un request adicional hacia un endpoint todavía no
definido.

### Qué construí
- `apps/argocd-diagnostician/`: la imagen (Python + kubectl), el Deployment y el
  Service, los RBAC (ClusterRole de solo lectura sobre Applications, pods, logs,
  eventos, deployments, ...) y el `WorkflowTemplate` `argocd-diagnose` (namespace
  `argo`).
- El primer paso del workflow **invoca el Deployment a través de su Service**
  (`diagnostician.py --via-service ...`) en vez de duplicar la lógica dentro del
  pod del workflow; el informe viaja al segundo paso como parámetro.
- `apps/webhook/`: el webhook dejó de solo loggear; ahora crea un `Workflow` a
  partir del template (hablando con la API in-cluster, sin kubectl) para la app
  que llega en la notificación y **no lanza otro si ya hay uno activo** para esa
  misma app.
- RBAC nuevos: el SA de los pods del workflow puede crear `workflowtaskresults`
  y el SA del webhook puede crear/listar workflows en `argo`.

### Errores y cosas que asumí sin comprobar
- **`HTTPServer` es mono-hilo y con `HTTP/1.1` keep-alive bloquea las sondas.** El
  pod del diagnóstico arrancaba, respondía `/healthz` con 200 un par de veces y
  luego readiness/liveness empezaban a dar timeout ("context deadline exceeded")
  aunque el server siguiera vivo. Lo resolví con `ThreadingHTTPServer`: una
  conexión atascada bloqueaba a todas las demás.
- **Después falló el RBAC:** `workflowtaskresults.argoproj.io is forbidden: User
  "system:serviceaccount:argo:argocd-diagnostician" cannot create resource
  "workflowtaskresults"`. Los pods de un Workflow reportan sus salidas creando
  `workflowtaskresults`; el chart de argo-workflows crea el Role con ese permiso
  pero no lo enlaza a un ServiceAccount propio. Añadí Role + RoleBinding en `argo`.
- **Asumí que podía usar un artefacto de salida sin repositorio de artefactos.**
  Error: `artifact storage is not configured`. Como el informe es pequeño (~20KB)
  lo pasé como **parámetro** (`outputs.parameters` + `valueFrom.path`), que no
  necesita MinIO/S3.
- **El controller de ArgoCD (sharding, 2 réplicas) se quedaba en `OOMKilled` con
  512Mi** a mitad de un sync y lo reiniciaba desde cero: las operaciones de sync
  quedaban en `Running` para siempre y el `argocd-diagnostician` no llegaba a
  crearse. Subí el límite a 1Gi. Además el StatefulSet se había quedado en
  deadlock (no recrea un pod que nunca está Ready): hubo que borrar el pod a mano
  para que la rolling update arrancara con el límite nuevo.

### Cómo queda funcionando
- ArgoCD (`app-error-test` en Degraded) → notifications → webhook → crea el
  Workflow `argocd-diagnose-*` → paso 1 (el Deployment) diagnostica y prepara el
  request → paso 2 recibe el informe. Verificado de punta a punta:
  `forward.defined=false` (endpoint aún sin definir) y `signatures=25` con
  categorías `CrashLoopBackOff`, `ProbeFailed` y `ProgressDeadlineExceeded`.
- Dedup: un segundo POST mientras hay un workflow activo devuelve
  `action=skipped`.
- El servicio deja el informe como **archivo dentro de su propio pod**
  (`/tmp/report.json`, configurable con `REPORT_FILE`). Como el pod del Deployment
  está siempre `Running`, se lee directo (sin jsonpath):
  `kubectl -n apps exec deploy/argocd-diagnostician -- cat /tmp/report.json`.
  Ojo: un pod ya **terminado** no se puede `exec`-ear, así que dejar el archivo en
  los pods del workflow no sirve para leerlo después.
- Las **ejecuciones** se ven en la UI de Argo Workflows, expuesta en
  `https://workflows.lab.test` (Ingress + Certificate siguiendo el patrón de
  `argocd.lab.test`). No aparecen en ArgoCD: los `Workflow` se crean en caliente,
  no están en Git y no llevan la label `argocd.argoproj.io/instance`, así que no
  pertenecen a ninguna Application (en ArgoCD solo se ve el `WorkflowTemplate`).
  El server usa `auth-mode server`: hay que pegar un token
  (`kubectl -n argo create token argo-workflows-server --duration=24h`).
- Los pods del workflow se **conservan** (quité `podGC: OnPodCompletion`) hasta
  que el `ttlStrategy` (1h) borra el workflow, para poder revisar con
  `kubectl -n argo logs -l workflows.argoproj.io/workflow=<wf> -c main` lo que
  imprimió cada paso. El informe también queda en `describe wf`, bajo
  `Nodes → collect-diagnostics → Outputs → Parameters → report`.

### Afinado: diagnosticar cualquier tipo de recurso

El primer corte solo sabía mirar *workloads* (Deployment, Pod, Job, ...). Para
cualquier otra cosa —un `Certificate`, un `ExternalSecret`, un `Ingress`— el
diagnóstico no recolectaba nada: se quedaba en una nota. Y lo que es peor, si
ArgoCD no le calculaba salud al recurso (le pasa a los CRDs: el Certificate
aparece en `status.resources` con `status: Synced` y **sin campo `health`**), ni
siquiera entraba en la rama de la nota: se ignoraba por completo.

Generalicé la recolección a cualquier tipo:

- La salud de un recurso que no es workload se decide por **su propia condición
  de readiness** (`Ready`, `Available`, `Established`, `Bound`, ...), ignorando
  las condiciones que en `False` son normales (`Issuing` de cert-manager).
- Se recolecta `get` + `describe` + condiciones + eventos para **cualquier** kind.
- Se **sigue la cadena de recursos relacionados** hasta la causa raíz real:
  `Certificate` → `CertificateRequest` → `Order` → `Challenge`, más el issuer o
  el secret store referenciados (`issuerRef`, `secretStoreRef`). El error de ACME
  no está en la Certificate, está más abajo.
- Se soportan recursos cluster-scoped (`ClusterIssuer`, `ClusterSecretStore`) sin
  `-n`.
- Categorías nuevas: `CertIssuanceFailed`, `ExternalSecretSyncFailed`, `NotReady`.
- RBAC de lectura para `cert-manager.io`, `external-secrets.io` y
  `networking.k8s.io`.

Verificado de punta a punta con un `Certificate` que apunta a un ClusterIssuer
inexistente: el informe lo marcó (`Ready=False`), siguió la cadena
(`ClusterIssuer/does-not-exist`, `CertificateRequest/...`) y dejó la causa raíz
en las firmas: `Referenced "ClusterIssuer" not found`.

### Construir y cargar la imagen del diagnóstico (repetible)
```bash
docker build --provenance=false --sbom=false -t kubelab/argocd-diagnostician:1.0.0 apps/argocd-diagnostician
kind load docker-image --name kubelab kubelab/argocd-diagnostician:1.0.0

# OJO: se reutiliza el tag 1.0.0, asi que `kind load` NO reinicia los pods que ya
# corren. Si el commit no cambia la plantilla del Deployment, no hay rollout y el
# pod sigue con la imagen vieja. Para que coja la nueva, recrear el pod:
kubectl -n apps delete pod -l app=argocd-diagnostician
```

---

## Aprendizajes consolidados hasta ahora

1. **Comprobar el entorno antes de actuar:** permisos (`ls -ld`), contexto
   (`kubectl config current-context`), puertos (`ss -ltn`).
2. **Timeouts realistas:** un cluster KinD de 3 nodos no se crea en 3 minutos.
3. **Aislar variables al depurar:** un cluster mínimo sin patches confirmó la
   causa del fallo del kubelet.
4. **Menos es más:** el patch de kubeadm no aportaba nada y rompió el cluster.
5. **No diagnosticar un fallo sin esperar al controller:** el ClusterIssuer
   pasó de `False` a `True` en segundos.
6. **CRDs primero:** los CRDs de un controller son un prerequisito explícito,
   no parte del kustomization del recurso.
7. **No asumir que un error de conexión es del cluster nuevo:** verificar de
   qué contexto viene antes de tocar nada.
8. **KinD no tiene LoadBalancer nativo:** usar hostPort + nodeSelector +
   toleration, o el manifiesto oficial para KinD.
9. **Musl vs glibc en hashes de password:** las imágenes Alpine solo soportan
   `$1$`, `$5$`, `$6$` en `crypt()`. `htpasswd` genera `$apr1$` (glibc) que falla
   silenciosamente con "password mismatch".
10. **No mezclar `kubectl create --from-file` con `kubectl apply` en el mismo
    secret:** produce merge de datos y archivos corruptos.
11. **Usar manifiestos oficiales de los proveedores para entornos concretos:**
    ingress-nginx publica uno específico para KinD. No reinventar.
12. **Rollout restart en pods con hostPort causa deadlock:** usar scale down/up
    para liberar puertos.
13. **Sin registro, las imágenes de un lab KinD se cargan con
    `kind load docker-image`** (+ `imagePullPolicy: IfNotPresent`) y conviene
    construir con `--provenance=false --sbom=false` para evitar manifest lists
    con attestations que el kubelet no resuelve.
14. **ArgoCD solo reporta Degraded (Deployment) con `ProgressDeadlineExceeded`:**
    el rollout no debe llegar a completar. Si el pod alcanza a estar Ready, la app
    alterna `Healthy`/`Progressing` aunque crashee. `minReadySeconds` mayor que la
    vida del pod lo fuerza.
15. **`progressDeadlineSeconds` debe ser mayor que `minReadySeconds`** (validación
    del API server); si no, el sync de ArgoCD falla con `SyncError`.
16. **El ConfigMap de notificaciones puede ser propiedad del repo** habilitando el
    controller con `notifications.enabled=true` y `notifications.cm.create=false`
    en el chart `argo-cd`.
17. **Un `HTTP_Server` mono-hilo con `protocol_version = HTTP/1.1` se bloquea con
    las sondas:** una conexión keep-alive atascada impide atender a las demás y
    readiness/liveness dan timeout aunque el server responda. Usar
    `ThreadingHTTPServer`.
18. **Los pods de un Workflow necesitan crear `workflowtaskresults`** en el
    namespace del workflow para reportar salidas. El chart de argo-workflows crea
    el Role pero no lo enlaza a un SA propio: hay que crear el RoleBinding.
19. **`outputs.artifacts` de Argo requiere un repositorio de artefactos** (MinIO/
    S3). Para pasar datos pequeños (~20KB) entre pasos sin montar uno, usar
    `outputs.parameters` con `valueFrom.path`.
20. **Un controller de ArgoCD con memoria justa se OOMKilla a mitad de un sync** y
    lo reinicia desde cero: las operaciones quedan en `Running` para siempre y no
    se aplican recursos nuevos. Además, un `StatefulSet` no recrea un pod que
    nunca llega a `Ready`, así que la rolling update se queda en deadlock: hay que
    borrar el pod a mano para que arranque con el límite nuevo.
21. **Evitar repetir el mismo diagnóstico:** deduplicar la evidencia por firma
    normalizada (timestamps/ids/números colapsados) y no lanzar un workflow nuevo
    si ya hay uno activo para la misma Application.
22. **Un `timeoutSeconds` de sonda por defecto (1s) es poco para un servicio Python
    ocupado:** mientras atiende un `/diagnose` (subprocess + parseo de JSON) puede
    tardar más de 1s en responder `/healthz`; kubelet cierra la conexión (el server
    registra `BrokenPipeError`) y, tras 3 fallos, la liveness mata el pod. Dar
    margen (`timeoutSeconds`) y tragarse `BrokenPipeError`/`ConnectionResetError`
    en el handler: que un cliente corte la conexión no es un error del servicio.
23. **ArgoCD no calcula salud para la mayoría de CRDs.** Un `Certificate` aparece
    en `status.resources` con `status: Synced` y **sin campo `health`**, así que
    cualquier lógica que dependa de `health` lo ignora. Para recursos que no son
    workloads hay que leer **sus propias condiciones** (`Ready`, `Available`, ...).
24. **Ojo con las condiciones que en `False` son normales.** `Issuing=False` en
    una `Certificate` es lo habitual (no se está emitiendo); tratarla como fallo
    daría falsos positivos. Hay que ignorarla explícitamente.
25. **La causa raíz suele estar un nivel más abajo:** el error real de un
    `Certificate` aparece en su `CertificateRequest`/`Order`/`Challenge`, no en la
    Certificate. Seguir los `ownerReferences` (y el `issuerRef`/`secretStoreRef`)
    es lo que da el mensaje útil.
26. **Reutilizar el tag de la imagen en KinD engaña:** `kind load docker-image`
    actualiza la imagen en containerd, pero los pods ya en ejecución siguen con
    la vieja, y si el commit no cambia la plantilla del Deployment no hay rollout.
    Hay que recrear el pod (`kubectl delete pod -l ...`) para probar el código nuevo.

---

*Seguirá actualizándose en cada fase del despliegue.*
