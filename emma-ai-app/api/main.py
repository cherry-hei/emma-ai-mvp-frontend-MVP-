"""Emma AI REST API.

Thin HTTP layer over emma_core.services (same logic the Reflex UI calls
in-process). Grows to cover the documented endpoint contract; for the Phase 0/1
slice it exposes a health check and is wired for routers.
"""
from fastapi import FastAPI

app = FastAPI(title="Emma AI API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emma-ai-api"}
