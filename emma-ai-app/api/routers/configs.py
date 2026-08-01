"""/facility-configs and the shift dictionary writes (spec 2.2 / 2.3).

Reads are open to any signed-in user of the facility - the roster grid and the
staff app both need to know what a duty code means. Writes are restricted, and
every write is audited: a changed cycle or duty window silently alters what the
compliance engine measures.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import FacilityConfigRequest, ShiftDefinitionRequest
from emma_core.services import audit
from emma_core.services import facility_config as svc

router = APIRouter(tags=["configs"])
WRITE_ROLES = {"superintendent", "admin"}


def _require_write_role(ctx: AuthCtx) -> None:
    if str(ctx.profile.role) not in WRITE_ROLES:
        raise api_error(403, "forbidden",
                        "Only a superintendent or admin may change facility configuration.")


@router.get("/facility-configs")
def list_configs(config_key: str | None = Query(default=None),
                 include_history: bool = Query(default=False),
                 ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_configs(ctx.client, ctx.facility_id, config_key=config_key,
                            include_history=include_history)


@router.get("/facility-configs/keys")
def config_keys():
    """The config keys the platform itself reads. Others are allowed but ignored."""
    return [{"config_key": key} for key in svc.KNOWN_KEYS]


@router.post("/facility-configs", status_code=201)
def put_config(body: FacilityConfigRequest, ctx: AuthCtx = Depends(get_ctx)):
    """Publish a new version of one config key, retiring the previous one."""
    _require_write_role(ctx)
    previous = svc.get_config(ctx.client, ctx.facility_id, body.config_key)
    row = svc.put_config(
        ctx.client, ctx.facility_id, config_key=body.config_key,
        config_json=body.config_json, description=body.description,
        effective_from=body.effective_from, created_by=ctx.profile_id,
    )
    audit.record(ctx.client, facility_id=ctx.facility_id, action="update",
                 entity_table="facility_json_configs", entity_id=row["id"],
                 before=previous, after=row, actor_profile_id=ctx.profile_id,
                 actor_email=ctx.profile.email,
                 reason=f"{body.config_key} v{row['version']}")
    return row


@router.post("/shift-definitions", status_code=201)
def upsert_shift_definition(body: ShiftDefinitionRequest,
                            ctx: AuthCtx = Depends(get_ctx)):
    """Create or update one duty code for this facility."""
    _require_write_role(ctx)
    row = svc.upsert_shift_definition(
        ctx.client, ctx.facility_id, shift_type=body.shift_type, label=body.label,
        start_time=body.start_time, end_time=body.end_time,
        segments=[s.model_dump() for s in body.segments] if body.segments else None,
        is_working=body.is_working, weighting_factor=body.weighting_factor,
        paid_minutes_override=body.paid_minutes, source_note=body.source_note,
    )
    audit.record(ctx.client, facility_id=ctx.facility_id, action="update",
                 entity_table="shift_definitions", entity_id=row["id"], after=row,
                 actor_profile_id=ctx.profile_id, actor_email=ctx.profile.email,
                 reason=f"shift definition {body.shift_type}")
    return row
