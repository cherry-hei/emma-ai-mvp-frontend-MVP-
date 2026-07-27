# syntax=docker/dockerfile:1
#
# Production image for the Emma AI REST API (FastAPI + uvicorn).
#
# The frontend is a separate Next.js app (repo `main`); this container serves
# ONLY the JSON API. The ECS Express Mode load balancer terminates HTTPS and
# forwards to the container port — no reverse proxy or static-file serving is
# needed, so there is no Caddy here.
#
# Config comes from environment variables (ECS task definition):
#   SUPABASE_URL, SUPABASE_ANON_KEY, APP_ENV, CORS_ORIGINS (comma-separated
#   Next.js origins) as plain env; SUPABASE_SERVICE_ROLE_KEY and DATABASE_URL
#   injected from Secrets Manager. See SETUP_BACKEND_AWS.md.
#
# Build context = repo ROOT (the image needs emma-ai-app/).

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
