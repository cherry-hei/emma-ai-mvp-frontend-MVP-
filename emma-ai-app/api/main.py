"""Emma AI REST API — thin routers over emma_core.services, consumed by the Next.js app."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestAPIError

from emma_core.config import settings

from api.routers import analytics as _analytics
from api.routers import auth as _auth
from api.routers import compliance as _compliance
from api.routers import incidents as _incidents
from api.routers import leave as _leave
from api.routers import me as _me
from api.routers import optimize as _optimize
from api.routers import reports as _reports
from api.routers import residents as _residents
from api.routers import roster as _roster
from api.routers import staff as _staff

app = FastAPI(title="Emma AI API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PostgrestAPIError)
def _postgrest_error(_request: Request, exc: PostgrestAPIError) -> JSONResponse:
    # Surface only the message — hint/details can leak schema internals.
    message = getattr(exc, "message", None) or "database error"
    return JSONResponse(status_code=500,
                        content={"detail": {"code": "db_error", "message": message}})


@app.exception_handler(ValueError)
def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
    # Services raise ValueError for bad input — map to 422, not a 500 traceback.
    return JSONResponse(status_code=422,
                        content={"detail": {"code": "invalid_input", "message": str(exc)}})

for _module in (_auth, _roster, _residents, _compliance, _staff, _optimize,
                _leave, _incidents, _me, _analytics, _reports):
    app.include_router(_module.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emma-ai-api"}
