"""Emma AI REST API.

The HTTP surface the Next.js frontend consumes. Thin routers over
``emma_core.services`` (the same domain logic; the Reflex UI that used to call it
in-process has been removed). Routers are included directly so a broken router
fails loudly at startup rather than serving a crippled API behind a healthy /health.

CORS is required: the Next.js app is a separate browser origin. Allowed origins
come from the CORS_ORIGINS setting (see emma_core.config).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestAPIError

from emma_core.config import settings

from api.routers import auth as _auth
from api.routers import compliance as _compliance
from api.routers import optimize as _optimize
from api.routers import residents as _residents
from api.routers import roster as _roster
from api.routers import staff as _staff

app = FastAPI(title="Emma AI API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PostgrestAPIError)
def _postgrest_error(_request: Request, exc: PostgrestAPIError) -> JSONResponse:
    """Turn a raw PostgREST/DB error into a clean 500 with our {code,message}
    shape. Surface only the message — never exc.hint/exc.details, which can leak
    schema internals to the client."""
    message = getattr(exc, "message", None) or "database error"
    return JSONResponse(status_code=500,
                        content={"detail": {"code": "db_error", "message": message}})


@app.exception_handler(ValueError)
def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
    """Services raise ValueError for bad client input (unknown period, no source
    roster version). Map it to 422 instead of a 500 traceback."""
    return JSONResponse(status_code=422,
                        content={"detail": {"code": "invalid_input", "message": str(exc)}})

for _module in (_auth, _roster, _residents, _compliance, _staff, _optimize):
    app.include_router(_module.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emma-ai-api"}
