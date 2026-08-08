# Troubleshooting

## Cluster no responde

```bash
kind get clusters
docker ps
kubectl cluster-info
```

Si el API server no responde, reconstruir el cluster:

```bash
make destroy && make bootstrap
```

## cert-manager no emite certificados

Verificar:

```bash
kubectl get certificates -A
kubectl describe certificate <name> -n <ns>
kubectl get clusterissuers
```

## Traefik no enruta

Verificar IngressClass e Ingress:

```bash
kubectl get ingressclass
kubectl get ingress -A
kubectl -n traefik logs deploy/traefik --tail=50
```

## Certificado no válido en el navegador

La CA interna (`lab-root-ca`) debe importarse en el trust store del sistema
o usar la opción de "continuar" del navegador. El certificado se emite para
`*.lab.test` (wildcard), por lo que `https://traefik.lab.test` debe funcionar
si `traefik.lab.test` resuelve a 127.0.0.1 en `/etc/hosts`.

## Kyverno policies en Audit

Las policies empiezan en modo `Audit`. Para ver violaciones:

```bash
kubectl get clusterpolicyreports
```

## ArgoCD no sincroniza

```bash
kubectl -n argocd get applications
kubectl -n argocd describe application kubelab
kubectl -n argocd logs deploy/argocd-server --tail=50
```
