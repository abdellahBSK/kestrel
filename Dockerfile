# syntax=docker/dockerfile:1

# ── Build the web app ──────────────────────────────────────────────
FROM node:24-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Runtime: Python standard library only ─────────────────────────
FROM python:3.13-slim
LABEL org.opencontainers.image.title="Kestrel" \
      org.opencontainers.image.description="Mission control for AI agents" \
      org.opencontainers.image.source="https://github.com/abdellahBSK/kestrel" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KESTREL_HOME=/data \
    KESTREL_HOST=0.0.0.0

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY --from=web /app/src/kestrel/static/ src/kestrel/static/
RUN pip install --no-cache-dir . && rm -rf /src \
 && useradd --create-home --uid 10001 kestrel && mkdir -p /data && chown kestrel /data

USER kestrel
WORKDIR /data
VOLUME ["/data"]
EXPOSE 7777

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:7777/v1/health', timeout=2)" || exit 1

# Publish the port on the host's loopback only: docker run -p 127.0.0.1:7777:7777 ...
ENTRYPOINT ["kestrel"]
CMD ["watch", "--no-browser"]
