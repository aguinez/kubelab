FROM python:3.12-slim

ARG KUBECTL_VERSION=v1.31.0
ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL -o /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
 && chmod +x /usr/local/bin/kubectl \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home appuser

WORKDIR /app
COPY diagnostician.py /app/diagnostician.py

USER 1000

EXPOSE 8080

CMD ["python", "/app/diagnostician.py"]
