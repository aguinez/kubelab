# AI Platform Engineering Rules

Estas reglas son obligatorias para cualquier agente de IA que opere esta plataforma.

1. **Never modify Kubernetes resources manually if they are GitOps managed.**

2. **Never use kubectl apply for resources managed by ArgoCD.**

3. **Every infrastructure change must be represented in Git.**

4. **Never store secrets in Git.**

5. **Never use :latest images.**

6. **Every workload must have resource requests and limits.**

7. **Every workload must run as non-root unless explicitly justified.**

8. **Every externally exposed application must use TLS.**

9. **Every new namespace requires explicit justification.**

10. **Before modifying the cluster:**
    - Inspect current state.
    - Identify resource ownership.
    - Modify Git.
    - Validate manifests.
    - Synchronize ArgoCD.
    - Verify resulting state.

## Desired AI Workflow

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

El objetivo es que la IA actúe como un **Platform Engineer Agent**,
no simplemente como un ejecutor de comandos `kubectl`.
