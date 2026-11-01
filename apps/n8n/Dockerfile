# n8n con kubectl y jq para que el flujo pueda consultar la API de Kubernetes
# (kubectl get/describe/logs, events...) usando la ServiceAccount `n8n`.
#
# La imagen base es una "Docker Hardened Image (Alpine)" que NO trae `apk`, asi
# que kubectl y jq se instalan como binarios estaticos descargados con wget.
FROM docker.n8n.io/n8nio/n8n:2.45.4

USER root

ARG KUBECTL_VERSION=v1.31.0
ARG JQ_VERSION=1.7.1
ARG TARGETARCH=amd64

RUN wget -q -O /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
 && wget -q -O /usr/local/bin/jq \
      "https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-${TARGETARCH}" \
 && chmod +x /usr/local/bin/kubectl /usr/local/bin/jq

USER node
