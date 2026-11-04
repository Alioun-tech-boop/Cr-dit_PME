# syntax=docker/dockerfile:1
FROM python:3.12.14-slim
WORKDIR /app
# Le module local doit exister avant la résolution du chemin dans uv.lock.
COPY . .
RUN --mount=type=secret,id=proxy_ca \
    set -eu; \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    apt-get -o Acquire::https::CaInfo="${PIP_CERT:-/etc/ssl/certs/ca-certificates.crt}" update; \
    apt-get -o Acquire::https::CaInfo="${PIP_CERT:-/etc/ssl/certs/ca-certificates.crt}" install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra; \
    rm -rf /var/lib/apt/lists/*; \
    pip install --no-cache-dir uv==0.9.8; \
    uv sync --locked --no-dev --no-cache; \
    groupadd --gid 10001 creditapp; \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin creditapp; \
    chmod -R a+rX /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
CMD ["python", "-m", "credit.security.entrypoint"]
