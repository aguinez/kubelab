# Arquitectura

## Vista general

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

## Componentes

| Componente   | Responsabilidad                    | Namespace     |
| ------------ | ---------------------------------- | ------------- |
| KinD         | Kubernetes local                   | —             |
| Docker       | Runtime del laboratorio            | —             |
| cert-manager | Gestión automática de certificados | cert-manager  |
| Internal CA  | PKI interna del laboratorio        | cert-manager  |
| Traefik      | Ingress Controller                 | traefik       |
| Kyverno      | Kubernetes Policy Engine           | kyverno       |
| ArgoCD       | GitOps / Continuous Delivery       | argocd        |

## PKI interna

```text
Root CA (self-signed, ECDSA)
   │
   ▼
ClusterIssuer (lab-issuer)
   │
   ├── argocd.lab.test
   ├── traefik.lab.test
   └── *.lab.test
```

## Dominio interno

* `*.lab.test`
* Inicialmente resuelto via `/etc/hosts`
* Posteriormente reemplazado por DNS interno

## Flujo GitOps

```text
Git
 │
 ▼
ArgoCD
 │
 ▼
Kubernetes
```
