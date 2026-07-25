# syntax=docker/dockerfile:1
#
# Production image for the Emma AI Reflex dashboard (single-container pattern).
#
#   Caddy  ── serves the exported static frontend on $PORT (8080)
#          └─ reverse-proxies backend routes (/_event websocket, /ping, /_upload)
#   Reflex ── runs the Python backend on :8000  (`reflex run --env prod --backend-only`)
#
# AWS App Runner terminates HTTPS and forwards to $PORT, so the whole app is one
# origin. The public URL is injected at RUNTIME via the API_URL env var (see
# deploy/docker-entrypoint.sh): App Runner only assigns the URL after the service
# is created, so the frontend is (re)baked at container start, not at build time.
#
# Build context = repo ROOT. In App Runner set: Dockerfile = ./Dockerfile.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    BACKEND_PORT=8000

# ── system deps: Caddy (official apt repo) + tools reflex/ortools may need ──
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl gnupg unzip ca-certificates \
      debian-keyring debian-archive-keyring apt-transport-https \
 && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
 && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      > /etc/apt/sources.list.d/caddy-stable.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends caddy \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (separate layer so code changes don't re-install everything) ──
COPY emma-ai-app/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# ── app source ──
COPY emma-ai-app/ ./

# ── warm the frontend toolchain: downloads bun + node deps and does a first
#    compile, so the runtime re-export (with the real public URL) is fast.
#    No DB is touched here; config falls back to defaults when no .env exists. ──
RUN reflex init && reflex export --frontend-only --no-zip

# ── reverse-proxy config + entrypoint ──
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
 && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080
CMD ["/usr/local/bin/entrypoint.sh"]
