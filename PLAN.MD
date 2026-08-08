# Etapa 1 — Kubernetes Platform Bootstrap

## Objetivo

Construir una plataforma Kubernetes local, reproducible y GitOps-first sobre **KinD**, que sirva como base para las siguientes etapas del laboratorio.

Al finalizar esta etapa tendremos:

* KinD con 3 nodos.
* `cert-manager`.
* CA interna para certificados TLS.
* Dominio interno `*.lab.test`.
* Traefik como Ingress Controller.
* HTTPS automático.
* Kyverno como Policy Engine.
* ArgoCD como plataforma GitOps.
* Estructura de repositorio preparada para evolucionar hacia una plataforma cloud-native completa.

---

# 1. Arquitectura

```text
                         Local Machine
                              │
                           Docker
                              │
                             KinD
                              │
              ┌───────────────┼────────────────┐
              │               │                │
       cert-manager         Traefik          Kyverno
              │               │                │
          Internal CA       Ingress          Policies
              │               │                │
              └───────────────┼────────────────┘
                              │
                            ArgoCD
                              │
                         GitOps Control
                              │
                              ▼
                         Kubernetes
```

---

# 2. Componentes

| Componente   | Responsabilidad                    |
| ------------ | ---------------------------------- |
| KinD         | Kubernetes local                   |
| Docker       | Runtime del laboratorio            |
| cert-manager | Gestión automática de certificados |
| Internal CA  | PKI interna del laboratorio        |
| Traefik      | Ingress Controller                 |
| Kyverno      | Kubernetes Policy Engine           |
| ArgoCD       | GitOps / Continuous Delivery       |

---

# 3. Estructura del repositorio

```text
k8s-platform-lab/
│
├── README.md
├── Makefile
├── .gitignore
│
├── bootstrap/
│   └── kind/
│       ├── cluster.yaml
│       └── create.sh
│
├── clusters/
│   └── local/
│       ├── kustomization.yaml
│       └── namespaces.yaml
│
├── platform/
│   ├── cert-manager/
│   ├── traefik/
│   ├── kyverno/
│   └── argocd/
│
├── policies/
│   └── kyverno/
│
└── docs/
    ├── architecture.md
    ├── ai-instructions.md
    └── troubleshooting.md
```

---

# 4. KinD

## 4.1 Cluster

Crear un cluster KinD de 3 nodos:

```text
kind-control-plane
kind-worker
kind-worker
```

La configuración debe permitir posteriormente:

* Scheduling.
* Node affinity.
* Anti-affinity.
* DaemonSets.
* Alta disponibilidad.
* Service Mesh.
* OpenTelemetry.
* Simulación de fallos de nodos.

## 4.2 Puertos

Exponer:

```text
80  → HTTP
443 → HTTPS
```

El tráfico deberá llegar posteriormente a Traefik.

## 4.3 Validación

```bash
kubectl cluster-info
kubectl get nodes
kubectl get pods -A
```

Expected:

```text
3 nodes
3 Ready
```

---

# 5. Namespaces

Crear explícitamente:

```text
cert-manager
traefik
kyverno
argocd
```

Los componentes de plataforma deben utilizar namespaces dedicados.

---

# 6. cert-manager

Instalar:

```text
cert-manager
cert-manager-webhook
cert-manager-cainjector
```

Validar:

```bash
kubectl get pods -n cert-manager
```

Todos los componentes deben estar `Running` / `Ready`.

---

# 7. Internal PKI

Crear una CA interna para el laboratorio.

Arquitectura:

```text
Root CA
   │
   ▼
ClusterIssuer
   │
   ├── argocd.lab.test
   ├── traefik.lab.test
   └── *.lab.test
```

Crear:

```text
lab-root-ca
```

y un:

```text
ClusterIssuer
```

para emitir certificados internos.

---

# 8. Internal Domain

Utilizar:

```text
*.lab.test
```

Ejemplos:

```text
argocd.lab.test
traefik.lab.test
app.lab.test
```

Inicialmente la resolución puede realizarse mediante `/etc/hosts`.

Ejemplo:

```text
127.0.0.1 argocd.lab.test
127.0.0.1 traefik.lab.test
```

Posteriormente esto será reemplazado por DNS interno.

---

# 9. Traefik

Instalar Traefik como Ingress Controller.

## Requisitos

* Kubernetes CRD provider.
* `IngressClass`.
* HTTP.
* HTTPS.
* TLS.
* HTTP → HTTPS redirect.
* Access logs.
* Dashboard.

Arquitectura:

```text
Browser
   │
   │ HTTPS
   ▼
localhost:443
   │
   ▼
Traefik
   │
   ├── argocd.lab.test
   │       │
   │       ▼
   │     ArgoCD
   │
   └── traefik.lab.test
           │
           ▼
        Dashboard
```

El dashboard no debe quedar expuesto sin autenticación.

---

# 10. Kyverno

Instalar Kyverno como Policy Engine.

Las primeras policies serán deliberadamente simples.

## 10.1 Required Labels

Los workloads deberán tener:

```yaml
app:
owner:
environment:
```

---

## 10.2 Disallow `latest`

Prohibir:

```yaml
image: nginx:latest
```

Preferir:

```yaml
image: nginx:<version>
```

o imágenes identificadas mediante digest.

---

## 10.3 Non-root

Los workloads deben ejecutarse como usuario no privilegiado.

Prohibir:

```yaml
runAsUser: 0
```

salvo excepciones explícitas.

---

## 10.4 Privileged Containers

Prohibir:

```yaml
securityContext:
  privileged: true
```

---

## 10.5 Resource Requests / Limits

Los workloads deben declarar:

```yaml
resources:
  requests:
    cpu:
    memory:

  limits:
    cpu:
    memory:
```

---

# 11. Policy Enforcement

Las policies deben introducirse progresivamente.

Primero:

```text
Audit
```

Después:

```text
Enforce
```

El objetivo es experimentar con ambos modelos y entender sus implicaciones operacionales.

---

# 12. ArgoCD

Instalar ArgoCD.

A partir de este punto, la arquitectura cambia:

### Antes

```text
AI
 │
 └── kubectl / Helm
       │
       ▼
   Kubernetes
```

### Después

```text
Git
 │
 ▼
ArgoCD
 │
 ▼
Kubernetes
```

ArgoCD será la fuente de reconciliación del estado deseado.

---

# 13. GitOps

Crear:

```text
clusters/local/
```

con una estructura similar a:

```text
clusters/
└── local/
    ├── kustomization.yaml
    ├── cert-manager.yaml
    ├── traefik.yaml
    ├── kyverno.yaml
    └── argocd.yaml
```

Y:

```text
platform/
├── cert-manager/
├── traefik/
├── kyverno/
└── argocd/
```

Arquitectura:

```text
clusters/local
       │
       ▼
    ArgoCD
       │
       ├── cert-manager
       ├── Traefik
       ├── Kyverno
       └── ArgoCD
```

---

# 14. AI Platform Engineering Rules

Crear:

```text
docs/ai-instructions.md
```

La IA deberá seguir estas reglas:

```text
1. Never modify Kubernetes resources manually if they are GitOps managed.

2. Never use kubectl apply for resources managed by ArgoCD.

3. Every infrastructure change must be represented in Git.

4. Never store secrets in Git.

5. Never use :latest images.

6. Every workload must have resource requests and limits.

7. Every workload must run as non-root unless explicitly justified.

8. Every externally exposed application must use TLS.

9. Every new namespace requires explicit justification.

10. Before modifying the cluster:
    - Inspect current state.
    - Identify resource ownership.
    - Modify Git.
    - Validate manifests.
    - Synchronize ArgoCD.
    - Verify resulting state.
```

---

# 15. Desired AI Workflow

Cada cambio solicitado a la IA debería seguir:

```text
Change requested
       │
       ▼
Inspect cluster
       │
       ▼
Identify ownership
       │
       ▼
Modify Git
       │
       ▼
YAML validation
       │
       ▼
Kustomize build
       │
       ▼
Kyverno validation
       │
       ▼
Git commit
       │
       ▼
ArgoCD sync
       │
       ▼
Kubernetes verification
       │
       ▼
Health check
```

El objetivo es que la IA actúe como un **Platform Engineer Agent**, no simplemente como un ejecutor de comandos `kubectl`.

---

# 16. Makefile

El proyecto debería terminar teniendo comandos simples:

```bash
make bootstrap
make validate
make status
make destroy
```

## Bootstrap

```bash
make bootstrap
```

Debe:

1. Validar prerequisitos.
2. Crear KinD.
3. Instalar componentes base.
4. Configurar certificados.
5. Configurar Traefik.
6. Configurar Kyverno.
7. Configurar ArgoCD.
8. Configurar GitOps.
9. Ejecutar validaciones.

## Validate

```bash
make validate
```

Debe validar:

* Nodes.
* Pods.
* Certificates.
* ClusterIssuers.
* Ingress.
* Kyverno policies.
* ArgoCD applications.
* TLS.
* HTTP/HTTPS connectivity.

## Status

```bash
make status
```

Debe proporcionar una visión resumida del estado de la plataforma.

## Destroy

```bash
make destroy
```

Debe eliminar completamente el laboratorio.

---

# 17. Definition of Done

La Etapa 1 se considera terminada cuando:

```text
✓ KinD cluster creado
✓ 3 Kubernetes nodes Ready
✓ cert-manager instalado
✓ Internal CA funcionando
✓ ClusterIssuer funcionando
✓ *.lab.test configurado
✓ Traefik instalado
✓ HTTP → HTTPS funcionando
✓ TLS funcionando
✓ Kyverno instalado
✓ Security policies funcionando
✓ ArgoCD instalado
✓ GitOps funcionando
✓ Platform resources gestionados por Git
✓ AI instructions documentadas
✓ Bootstrap reproducible
✓ Destroy/recreate reproducible
```

---

# 18. Final Validation

Debe ser posible destruir completamente el laboratorio:

```bash
make destroy
```

y posteriormente reconstruirlo:

```bash
make bootstrap
```

sin realizar configuraciones manuales adicionales.

La prueba definitiva será:

```text
Empty machine
      │
      ▼
make bootstrap
      │
      ▼
     KinD
      │
      ├── cert-manager
      ├── Internal CA
      ├── Traefik
      ├── Kyverno
      └── ArgoCD
             │
             ▼
          GitOps
             │
             ▼
       Healthy Platform
```

---

# 19. Fuera del alcance de Etapa 1

No instalar todavía:

* Prometheus.
* Grafana.
* Loki.
* Tempo.
* OpenTelemetry.
* Istio.
* KEDA.
* Vault.
* External Secrets Operator.
* Crossplane.
* Cilium.
* Aplicaciones de negocio.

Estos componentes serán incorporados progresivamente en las siguientes etapas.

La prioridad de esta primera etapa es conseguir una **plataforma Kubernetes reproducible, segura, TLS-enabled y GitOps-first** antes de añadir complejidad.
