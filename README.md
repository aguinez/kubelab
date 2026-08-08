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

## Dominio interno (*.lab.test)

CoreDNS del cluster resuelve `*.lab.test` → `127.0.0.1` (wildcard) y se expone
fuera del cluster en el puerto `30535` (NodePort mapeado en el cluster.yaml).

* `argocd.lab.test` — ArgoCD UI
* `traefik.lab.test` — App demo nginx (ingress-nginx)

### Configurar tu PC (Windows/WSL2)

Opción A — **DNS real (recomendado):** añade la IP de WSL como DNS en tu
adaptador de red de Windows, apuntando al puerto del forwarder:

```text
Servidor DNS preferido: 172.17.177.146  (IP de tu distro WSL: `hostname -I`)
```

El puerto del DNS es `30535` (no el 53, que ya usa Windows). Para que Windows
use un puerto no estándar, se configura con el adaptador de red o un script
PowerShell como administrador:

```powershell
# en Windows (PowerShell como admin), adapta "Ethernet"
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses ("172.17.177.146")
# y el DNS del lab está en el puerto 30535 — Windows lo consulta si el DNS
# preferido no responde en 53, por eso se usa un forwarder adicional.
```

Opción B — **hosts manual (simple):** añade a `C:\Windows\System32\drivers\etc\hosts`:

```text
127.0.0.1 argocd.lab.test traefik.lab.test
```

Opción C — **script automático:** ejecuta desde WSL:

```bash
bash scripts/update-hosts.sh   # detecta los Ingress y actualiza ambos hosts
```

## GitOps

ArgoCD sincroniza el estado deseado desde el repo Git. Toda modificación
a la plataforma debe hacerse en Git y sincronizarse, nunca con `kubectl apply` directo
sobre recursos gestionados.
