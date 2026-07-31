"""Append-only audit trail (spec 1.3).

`manual_override_log` records roster-cell edits because the AI-acceptance KPI is
computed from them. This service is the general record every module writes to,
including the ones with no roster cell to point at: a rule change, an import, a
configuration version, a publish.

Rows are immutable. `trg_protect_audit_log` rejects any UPDATE or DELETE, so a
correction is expressed as a further append with the earlier row referenced in
`before_json` - which is what makes the log usable as submission evidence.

Retention is proposed at 7 years, subject to client/legal/SWD confirmation. A
PDPO deletion request is honoured where lawful, but statutory HR, SWD-audit and
record-keeping duties can require retention, so nothing here promises
unconditional deletion.
"""
from __future__ import annotations

import json
from datetime import date as Date

from ._common import iso

ACTIONS = ("create", "update", "delete", "publish", "import", "login", "export")


def record(client, *, facility_id: str, action: str, entity_table: str,
           entity_id: str | None = None, before: dict | None = None,
           after: dict | None = None, actor_profile_id: str | None = None,
           actor_email: str | None = None, reason: str | None = None,
           request_id: str | None = None) -> dict | None:
    """Append one audit row. Never raises into the caller's happy path.

    An audit write must not be able to fail the operation it is describing - a
    lost log line is a reportable defect, a rolled-back roster publish is an
    outage. Failures are swallowed and surfaced by the row simply not being there,
    which the evidence checklist tests for.
    """
    row = {
        "facility_id": facility_id, "actor_profile_id": actor_profile_id,
        "actor_email": actor_email, "action": action,
        "entity_table": entity_table, "entity_id": entity_id,
        "before_json": _jsonable(before), "after_json": _jsonable(after),
        "reason": reason, "request_id": request_id,
    }
    try:
        # SQL: insert into audit_logs (facility_id, actor_profile_id, actor_email,
        #        action, entity_table, entity_id, before_json, after_json,
        #        reason, request_id)
        #      values (...) returning *
        return client.table("audit_logs").insert(row).execute().data[0]
    except Exception:  # noqa: BLE001 - see docstring
        return None


def list_logs(client, facility_id: str, *, entity_table: str | None = None,
              entity_id: str | None = None, action: str | None = None,
              date_from: Date | str | None = None,
              date_to: Date | str | None = None,
              limit: int = 100) -> list[dict]:
    """Newest first, filtered the way an auditor asks: what changed on this record."""
    # SQL: select * from audit_logs
    #      where (facility_id = :facility_id or facility_id is null)
    #        [and entity_table = :entity_table] [and entity_id = :entity_id]
    #        [and action = :action]
    #        [and created_at >= :date_from] [and created_at < :date_to + 1 day]
    #      order by created_at desc
    #      limit :limit
    query = (client.table("audit_logs").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null"))
    if entity_table:
        query = query.eq("entity_table", entity_table)
    if entity_id:
        query = query.eq("entity_id", entity_id)
    if action:
        query = query.eq("action", action)
    if date_from:
        query = query.gte("created_at", f"{iso(date_from)}T00:00:00+00:00")
    if date_to:
        query = query.lte("created_at", f"{iso(date_to)}T23:59:59+00:00")
    return query.order("created_at", desc=True).limit(limit).execute().data


def _jsonable(value: dict | None) -> dict | None:
    """Dates and UUIDs come back from PostgREST as objects; jsonb needs text."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))
