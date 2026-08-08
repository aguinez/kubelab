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

---

*Seguirá actualizándose en cada fase del despliegue.*
