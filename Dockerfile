FROM python:3.12-slim

ARG KUBECTL_VERSION=v1.31.2
ARG TARGETARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/kubectl \
       "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 assist
WORKDIR /srv/kubeassist

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kubeassist ./kubeassist
COPY knowledge ./knowledge
COPY run.py .

ENV KUBEASSIST_KUBECONFIG=/home/assist/.kube/config \
    KUBEASSIST_DATA_DIR=/srv/kubeassist/data \
    KUBEASSIST_HOST=0.0.0.0
RUN mkdir -p /srv/kubeassist/data && chown -R assist /srv/kubeassist
USER assist

EXPOSE 5000
# One worker keeps the in-memory rate limiter accurate; threads handle concurrency.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "run:app"]
