# k8s-platform-lab

Plataforma Kubernetes local, reproducible y GitOps-first sobre **KinD**.

## Estructura

```text
bootstrap/kind/       Configuración y creación del cluster
clusters/local/       Manifiestos base (namespaces, kustomization)
platform/             Manifiestos de componentes (cert-manager, ingress-nginx, kyverno, argocd)
policies/kyverno/     Policies del engine
docs/                 Documentación (arquitectura, instrucciones AI, troubleshooting)
```

## Requisitos

* Docker
* kind (v0.20+)
* kubectl (v1.28+)
* git

## Uso

```bash
make bootstrap   # crea el cluster e instala la plataforma
make validate    # valida el estado
make status      # resumen del estado
make destroy     # elimina el laboratorio
```

## Dominio interno

* `argocd.lab.test` — ArgoCD UI
* `traefik.lab.test` — App demo nginx (ingress-nginx)

Añadir a `/etc/hosts`:

```text
127.0.0.1 argocd.lab.test traefik.lab.test
```

## GitOps

ArgoCD sincroniza el estado deseado desde el repo Git. Toda modificación
a la plataforma debe hacerse en Git y sincronizarse, nunca con `kubectl apply` directo
sobre recursos gestionados.
