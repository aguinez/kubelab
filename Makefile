SHELL := /usr/bin/env bash
KIND_CLUSTER := kubelab
KIND_CONTEXT := kind-$(KIND_CLUSTER)
KUSTOMIZE := kubectl kustomize

.PHONY: help bootstrap validate status destroy

help:
	@echo "Objetivos disponibles:"
	@echo "  make bootstrap  - crear cluster + instalar plataforma completa"
	@echo "  make validate   - validar nodos, pods, certificados, ingress, policies"
	@echo "  make status     - resumen del estado de la plataforma"
	@echo "  make destroy    - eliminar el laboratorio por completo"

bootstrap:
	@bash bootstrap/kind/create.sh
	@kubectl --context $(KIND_CONTEXT) apply -k clusters/local
	@echo "==> Instalando cert-manager"
	@kubectl --context $(KIND_CONTEXT) apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
	@kubectl --context $(KIND_CONTEXT) -n cert-manager rollout status deploy/cert-manager --timeout=180s
	@kubectl --context $(KIND_CONTEXT) apply -k platform/cert-manager
	@echo "==> Instalando ingress-nginx"
	@kubectl --context $(KIND_CONTEXT) label node kubelab-control-plane ingress-ready=true --overwrite
	@kubectl --context $(KIND_CONTEXT) apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
	@kubectl --context $(KIND_CONTEXT) -n ingress-nginx wait --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s
	@kubectl --context $(KIND_CONTEXT) patch deploy -n ingress-nginx ingress-nginx-controller --type=strategic -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"kubelab-control-plane"}}}}}'
	@kubectl --context $(KIND_CONTEXT) -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=180s
	@kubectl --context $(KIND_CONTEXT) apply -k platform/ingress-nginx
	@echo "==> Instalando Kyverno"
	@helm repo add kyverno https://kyverno.github.io/kyverno 2>/dev/null || true
	@helm repo update kyverno 2>/dev/null || true
	@helm upgrade --install kyverno kyverno/kyverno -n kyverno --create-namespace --version 3.8.2
	@kubectl --context $(KIND_CONTEXT) -n kyverno rollout status deploy/kyverno-admission-controller --timeout=240s
	@kubectl --context $(KIND_CONTEXT) apply -k policies/kyverno
	@echo "==> Instalando ArgoCD"
	@helm repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
	@helm repo update argo 2>/dev/null || true
	@helm upgrade --install argocd argo/argo-cd -n argocd --version 10.3.0 --set server.extraArgs[0]=--insecure
	@kubectl --context $(KIND_CONTEXT) -n argocd rollout status deploy/argocd-server --timeout=240s
	@kubectl --context $(KIND_CONTEXT) apply -k platform/argocd
	@echo "==> Configurando GitOps"
	@bash scripts/gitops-init.sh
	@echo "==> Bootstrap completado"

validate:
	@echo "==> Nodes"
	@kubectl --context $(KIND_CONTEXT) get nodes -o wide
	@echo "==> Pods (plataforma)"
	@kubectl --context $(KIND_CONTEXT) get pods -A -o wide | grep -E 'cert-manager|ingress-nginx|kyverno|argocd' || true
	@echo "==> Certificados"
	@kubectl --context $(KIND_CONTEXT) get certificates -A
	@echo "==> ClusterIssuers"
	@kubectl --context $(KIND_CONTEXT) get clusterissuers
	@echo "==> Ingress"
	@kubectl --context $(KIND_CONTEXT) get ingress -A
	@echo "==> Policies Kyverno"
	@kubectl --context $(KIND_CONTEXT) get clusterpolicies
	@echo "==> ArgoCD Applications"
	@kubectl --context $(KIND_CONTEXT) -n argocd get applications 2>/dev/null || echo "  (sin applications todavía)"

status:
	@echo "==> Cluster: $(KIND_CLUSTER)"
	@kubectl --context $(KIND_CONTEXT) get nodes -o wide 2>/dev/null || echo "cluster no accesible"
	@echo "==> Namespaces de plataforma"
	@kubectl --context $(KIND_CONTEXT) get ns cert-manager ingress-nginx kyverno argocd 2>/dev/null
	@echo "==> Pods"
	@kubectl --context $(KIND_CONTEXT) get pods -A 2>/dev/null
	@echo "==> Certificados"
	@kubectl --context $(KIND_CONTEXT) get certificates -A 2>/dev/null
	@echo "==> Ingress"
	@kubectl --context $(KIND_CONTEXT) get ingress -A 2>/dev/null
	@echo "==> ClusterPolicies"
	@kubectl --context $(KIND_CONTEXT) get clusterpolicies 2>/dev/null
	@echo "==> ArgoCD Applications"
	@kubectl --context $(KIND_CONTEXT) -n argocd get applications 2>/dev/null || true

destroy:
	@echo "==> Destruyendo cluster $(KIND_CLUSTER)"
	@kind delete cluster --name $(KIND_CLUSTER)
	@echo "==> Laboratorio eliminado"
