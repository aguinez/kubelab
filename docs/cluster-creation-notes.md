# Consideraciones y problemas al crear el cluster del laboratorio

Fecha: 2026-08-07
Cluster: `kubelab` (KinD, 3 nodos, K8s v1.31.0)

---

## 1. Problemas de permisos en el directorio del proyecto

**Síntoma:** El directorio `/home/aguinez/projects/kubelab` pertenecía a `root`
(`drwxr-xr-x root root`) y el usuario `aguinez` no tenía permisos de escritura.
`git init` fallaba con `Permission denied`.

**Solución:** El usuario ejecutó manualmente el cambio de propietario
(`chown`) del directorio. A partir de ahí el proyecto es editable.

**Lección:** Antes de empezar a trabajar sobre un directorio, verificar
propiedad y permisos (`ls -ld`), especialmente cuando el directorio fue
creado por otro proceso/usuario.

---

## 2. Repositorio Git remoto ya existente

El remoto `https://github.com/aguinez/kubelab` ya existía en GitHub (vacío,
sin ramas) y la shell estaba autenticada para acceder a él.

Se inicializó el repo local con `git init -b main` y se configuró
`git remote add origin https://github.com/aguinez/kubelab`.

---

## 3. Cluster KinD preexistente (`transfer-platform`)

En la máquina ya existía un cluster KinD llamado `transfer-platform`, con su
contexto configurado como **current** en el kubeconfig. Dicho cluster no
respondía: el API server (`127.0.0.1:35909`) devolvía `connection reset by peer`
y `kubectl get nodes` colgaba.

**Decisión:** No tocar ese cluster (pertenece a otro propósito). El laboratorio
usa un cluster dedicado llamado `kubelab`. El contexto de `transfer-platform`
quedó intacto; todos los comandos del lab usan `--context kind-kubelab`.

**Consecuencia:** Mientras el contexto actual del kubeconfig apunte a
`transfer-platform`, los comandos de `kubectl` sin `--context` muestran errores
de conexión y cuelgan. Para el lab siempre hay que usar el contexto
`kind-kubelab` (el Makefile lo hace explícito).

---

## 4. Primer intento de creación: timeout en `kind create cluster`

**Síntoma:** El primer `kind create cluster` se ejecutó con un timeout de 180 s.
El comando quedó cortado en la fase `Starting control-plane`. Los contenedores
Docker (`kubelab-control-plane`, `kubelab-worker`, `kubelab-worker2`) quedaron
creados y "Up", pero el cluster no quedó operativo:
  - No existía el contexto `kind-kubelab` en el kubeconfig (el `kind create`
    nunca llegó a escribirlo).
  - El API server del control-plane no respondía.

**Limpieza:** Se eliminó únicamente el cluster `kubelab` incompleto
(`kind delete cluster --name kubelab`), dejando `transfer-platform` intacto.

**Lección:** La creación de un cluster KinD de 3 nodos necesita más de 3
minutos (descarga de imagen, arranque de kubeadm, CNI y unión de workers).
Usar timeouts amplios (7-10 min) para `kind create`.

---

## 5. Segundo intento: kubelet no saludable (error de kubeadm)

**Síntoma:** Con timeout de 600 s, `kind create` falló en la fase
`Starting control-plane` con el error clásico de kubeadm:

```text
The kubelet is not healthy after 4m0.001000079s
The HTTP call equal to 'curl -sSL http://127.0.0.1:10248/healthz' returned error: ...
This error is likely caused by:
  - The kubelet is not running
  - The kubelet is unhealthy due to a misconfiguration of the node ...
```

**Causa raíz:** El `cluster.yaml` incluía un `kubeadmConfigPatch` que añadía
`node-labels: "node-role.kubernetes.io/control-plane="` al kubelet del
control-plane. Ese patch era **innecesario** (la label ya la pone KinD) y
rompía el arranque del kubelet.

**Cómo se diagnosticó:** Se aisló el problema creando un cluster de prueba
(`kubelab-test`) con la **misma topología de 3 nodos pero sin patches**:

```bash
kind create cluster --config /tmp/kind-min.yaml
```

El cluster mínimo arrancó perfectamente (CNI instalada, workers unidos).
Esto confirmó que la causa era el patch, no la configuración de red, Docker,
ni los puertos.

**Solución:** Eliminar el `kubeadmConfigPatch` del `cluster.yaml`. El archivo
final solo define:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kubelab
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
      - containerPort: 443
        hostPort: 443
  - role: worker
  - role: worker
```

Se eliminó el cluster de prueba antes de recrear el definitivo.

**Lección:** Evitar patches de kubeadm que no aporten valor real. La label
`node-role.kubernetes.io/control-plane` ya la gestiona KinD por defecto.
Cuando un nodo no arranca, aislar variables (un cluster sin patches) es la
forma más rápida de encontrar la causa.

---

## 6. Exposición de puertos 80/443

Los puertos 80 y 443 del host se verificaron **libres** antes de crear el
cluster (`ss -ltn`), y se mapearon al control-plane vía `extraPortMappings`:

```yaml
extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
```

Esto permite que Traefik (desplegado como `type: LoadBalancer` con
`externalTrafficPolicy` local en el control-plane) reciba tráfico HTTP/HTTPS
directamente desde el host.

---

## 7. Estado final del cluster

Verificación tras la creación exitosa:

```text
kubelab-control-plane   Ready   control-plane   v1.31.0
kubelab-worker          Ready   <none>          v1.31.0
kubelab-worker2         Ready   <none>          v1.31.0
```

- 3 nodos, todos `Ready`.
- API server sano: `kubectl get --raw=/readyz` → `ok`.
- Puertos 80/443 del host escuchando (proxy a los contenedores KinD).
- Namespaces base creados: `cert-manager`, `traefik`, `kyverno`, `argocd`.
- cert-manager v1.16.2 instalado y operativo (3 pods Running).

---

## 8. Errores de API server "fantasma" en las trazas

Durante el proceso aparecieron múltiples errores del tipo:

```text
Get "https://127.0.0.1:35909/api?timeout=32s": read tcp ...: connection reset by peer
```

**Aclaración:** Esos errores **no** provenían del cluster del laboratorio.
Provenían del API server del cluster `transfer-platform` (puerto 35909),
que es el contexto por defecto del kubeconfig y estaba caído. El cluster
`kubelab` nunca dio errores de conexión una vez creado correctamente.

Para operar el laboratorio sin ruido: `kubectl config use-context kind-kubelab`.

---

## 9. Decisiones clave de diseño

1. **Cluster dedicado** (`kubelab`), totalmente independiente de
   `transfer-platform`, para poder destruirlo y recrearlo sin impacto.
2. **Sin patches de kubeadm**: mantener el `cluster.yaml` mínimo y declarativo.
3. **Versiones fijadas**: kindest/node v1.31.0 (KinD v0.24.0), cert-manager
   v1.16.2. Versionar siempre los componentes para reproducibilidad.
4. **Reproducibilidad**: el proceso queda encapsulado en `make bootstrap`
   (que ejecuta `bootstrap/kind/create.sh`), con `make destroy` para el
   teardown completo.
