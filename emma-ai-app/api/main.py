"""Emma AI REST API - thin routers over emma_core.services, consumed by the Next.js app."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestAPIError

from emma_core.config import settings

from api.routers import analytics as _analytics
from api.routers import auth as _auth
from api.routers import calendar as _calendar
from api.routers import compliance as _compliance
from api.routers import configs as _configs
from api.routers import governance as _governance
from api.routers import imports as _imports
from api.routers import incidents as _incidents
from api.routers import leave as _leave
from api.routers import me as _me
from api.routers import notifications as _notifications
from api.routers import optimize as _optimize
from api.routers import reports as _reports
from api.routers import residents as _residents
from api.routers import roster as _roster
from api.routers import scheduling as _scheduling
from api.routers import staff as _staff
from api.routers import swaps as _swaps

app = FastAPI(title="Emma AI API", version="0.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# The Phase 5 compliance triggers enforce policy in the database, so they are the
# authority on outcomes the caller can actually fix: an over-drawn leave balance
# or a cross-tenant anchor is a rejected request, not a server fault. Map the
# SQLSTATEs those triggers raise deliberately; anything else stays a 500.
_DB_ERROR_STATUS = {
    "23514": (422, "policy_violation"),      # check_violation - rule refused it
    "22023": (422, "invalid_input"),         # invalid_parameter_value
    "23503": (422, "invalid_reference"),     # foreign_key_violation
    "23505": (409, "conflict"),              # unique_violation - e.g. re-publish
    "42501": (403, "forbidden"),             # insufficient_privilege
    "P0002": (404, "not_found"),             # no_data_found
}


@app.exception_handler(PostgrestAPIError)
def _postgrest_error(_request: Request, exc: PostgrestAPIError) -> JSONResponse:
    # Surface only the message - hint/details can leak schema internals.
    message = getattr(exc, "message", None) or "database error"
    status_code, code = _DB_ERROR_STATUS.get(
        str(getattr(exc, "code", "") or ""), (500, "db_error"))
    return JSONResponse(status_code=status_code,
                        content={"detail": {"code": code, "message": message}})


@app.exception_handler(ValueError)
def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
    # Services raise ValueError for bad input - map to 422, not a 500 traceback.
    return JSONResponse(status_code=422,
                        content={"detail": {"code": "invalid_input", "message": str(exc)}})

for _module in (_auth, _roster, _residents, _compliance, _staff, _optimize,
                _leave, _incidents, _me, _analytics, _reports, _scheduling,
                _imports, _calendar, _configs, _governance, _swaps,
                _notifications):
    app.include_router(_module.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emma-ai-api"}
