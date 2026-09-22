"""/organisations: which charity the caller belongs to, and its homes.

Open to any signed-in user, like /me. A staff member's app needs to know whose
home it is showing, and a superintendent of a charity with several homes needs
the list before they can pick one. Row level security does the scoping, so there
is no role gate here and nothing to leak.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.services import organisations as svc

router = APIRouter(tags=["organisations"])


@router.get("/organisations/current")
def current_organisation(ctx: AuthCtx = Depends(get_ctx)):
    row = svc.current(ctx.client)
    if not row:
        raise api_error(403, "no_organisation",
                        "This account is not attached to an organisation.")
    return row


@router.get("/organisations/current/facilities")
def current_organisation_facilities(ctx: AuthCtx = Depends(get_ctx)):
    return svc.homes(ctx.client)
