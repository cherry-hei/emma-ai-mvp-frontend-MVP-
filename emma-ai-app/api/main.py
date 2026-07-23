"""Emma AI REST API.

Thin HTTP layer over emma_core.services (same logic the Reflex UI calls
in-process). Grows to cover the documented endpoint contract; for the Phase 0/1
slice it exposes a health check plus the Phase 2 optimize router.

Requires fastapi>=0.116 (starlette 1.x compatible) — see requirements.txt. Routers
are included directly: a broken router should fail loudly at startup rather than
silently serving a crippled API behind a healthy /health.
"""
from fastapi import FastAPI

from api.routers import optimize as _optimize

app = FastAPI(title="Emma AI API", version="0.1.0")
app.include_router(_optimize.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emma-ai-api"}
