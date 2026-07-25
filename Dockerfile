# syntax=docker/dockerfile:1
#
# Production image for the Emma AI REST API (FastAPI + uvicorn).
#
# The frontend is a separate Next.js app (repo `main`); this container serves
# ONLY the JSON API. AWS App Runner terminates HTTPS and forwards to $PORT — no
# reverse proxy or static-file serving is needed, so there is no Caddy here.
#
# Config comes from environment variables (App Runner service config):
#   SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, APP_ENV,
#   CORS_ORIGINS (comma-separated Next.js origins). See AWS_DEPLOY.md.
#
# Build context = repo ROOT. In App Runner set: Dockerfile = ./Dockerfile.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# ── Python deps (separate layer so code changes don't re-install everything).
#    ortools / psycopg[binary] / supabase ship manylinux wheels — no apt build
#    toolchain required on the slim image. ──
COPY emma-ai-app/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# ── app source ──
COPY emma-ai-app/ ./

EXPOSE 8080
# App Runner injects $PORT. Single uvicorn worker keeps the in-process solver
# BackgroundTasks simple; scale horizontally via App Runner instances.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
