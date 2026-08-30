"""Manager offers emergency cover, staff answer, manager commits the winner.

The commit itself is `incidents.resolve_incident`, not a second copy of it. That
function already moves the shift, cancels the absent person's row, books the TOIL
debt and stamps the response time, and a parallel implementation here would drift
from it within a month.
"""
from __future__ import annotations

from . import audit, incidents, notifications as notify
from ._common import now_iso

OPEN_STATUSES = ("pending", "accepted")


def _offer(client, facility_id: str, offer_id: str) -> dict:
    rows = (client.table("replacement_offers").select("*")
            .eq("facility_id", facility_id).eq("id", offer_id).execute().data)
    if not rows:
        raise ValueError("offer not found")
    return rows[0]


def _incident(client, facility_id: str, incident_id: str) -> dict:
    # The raw row, not the decorated view: nothing here needs the joined names,
    # and the candidate engine wants the row as stored anyway.
    rows = (client.table("sl_incidents").select("*")
            .eq("facility_id", facility_id).eq("id", incident_id).execute().data)
    if not rows:
        raise ValueError("incident not found")
    incident = rows[0]
    if incident["replacement_status"] == "resolved":
        raise ValueError("incident is already resolved")
    if not incident.get("shift_id"):
        raise ValueError("incident has no roster shift to cover")
    return incident


def offer(client, facility_id: str, incident_id: str, *, staff_ids: list[str],
          profile_id: str | None = None, note: str | None = None) -> list[dict]:
    """Ask one or more eligible people to cover a vacant shift.

    Only names the engine has already cleared may be asked. Offering a shift to
    someone who would breach a rest rule creates a promise the approval step has
    to break, and the person has already rearranged their day by then.
    """
    incident = _incident(client, facility_id, incident_id)
    eligible = {
        c["candidate_staff_id"]: c
        for c in incidents.build_candidates(client, facility_id, incident)
        if c["compliance_ok"]
    }
    unknown = [s for s in staff_ids if s not in eligible]
    if unknown:
        raise ValueError(
            "these staff are not eligible cover for this shift: " + ", ".join(unknown))

    already = {
        row["offered_staff_id"]: row
        for row in (client.table("replacement_offers").select("*")
                    .eq("facility_id", facility_id)
                    .eq("incident_id", incident_id).execute().data)
    }
    created = []
    for staff_id in staff_ids:
        if staff_id in already and already[staff_id]["status"] in OPEN_STATUSES:
            continue
        candidate = eligible[staff_id]
        row = {
            "facility_id": facility_id, "incident_id": incident_id,
            "shift_id": incident["shift_id"], "offered_staff_id": staff_id,
            "offered_by": profile_id, "score": candidate.get("score"),
            "rank_required": candidate.get("rank"), "note": note,
            "status": "pending", "responded_at": None, "response_note": None,
        }
        if staff_id in already:
            saved = (client.table("replacement_offers").update(row)
                     .eq("facility_id", facility_id)
                     .eq("id", already[staff_id]["id"]).execute().data[0])
        else:
            saved = client.table("replacement_offers").insert(row).execute().data[0]
        created.append(saved)

        notify.push(client, facility_id, staff_id=staff_id,
                    event_type="replacement_offer",
                    title="Can you cover a shift?",
                    body=note, related_type="replacement_offer",
                    related_id=saved["id"])
    return created


def respond(client, facility_id: str, offer_id: str, *, staff_id: str,
            accept: bool, note: str | None = None) -> dict:
    """The staff member answers. Only the person asked may answer."""
    row = _offer(client, facility_id, offer_id)
    if row["offered_staff_id"] != staff_id:
        raise ValueError("this offer was made to someone else")
    if row["status"] not in OPEN_STATUSES:
        raise ValueError(f"this offer is {row['status']} and can no longer be answered")

    updated = (client.table("replacement_offers").update({
        "status": "accepted" if accept else "declined",
        "responded_at": now_iso(), "response_note": note,
    }).eq("facility_id", facility_id).eq("id", offer_id).execute().data[0])

    if row.get("offered_by"):
        notify.push(client, facility_id, profile_id=row["offered_by"],
                    event_type="replacement_offer_answered",
                    title="Cover offer accepted" if accept else "Cover offer declined",
                    body=note, related_type="replacement_offer", related_id=offer_id)
    return updated


def approve(client, facility_id: str, offer_id: str, *,
            profile_id: str | None = None, note: str | None = None) -> dict:
    """Commit an accepted offer, which is what actually changes the roster."""
    row = _offer(client, facility_id, offer_id)
    if row["status"] != "accepted":
        raise ValueError(f"only an accepted offer can be approved; this one is "
                         f"{row['status']}")

    result = incidents.resolve_incident(
        client, facility_id, row["incident_id"],
        replacement_staff_id=row["offered_staff_id"],
        profile_id=profile_id, auto=False, note=note)

    approved = (client.table("replacement_offers").update({
        "status": "approved", "approved_by": profile_id, "approved_at": now_iso(),
    }).eq("facility_id", facility_id).eq("id", offer_id).execute().data[0])

    # Everyone else who was asked is told, rather than left waiting on an answer
    # that is never coming.
    for other in (client.table("replacement_offers").select("*")
                  .eq("facility_id", facility_id)
                  .eq("incident_id", row["incident_id"]).execute().data):
        if other["id"] == offer_id or other["status"] not in OPEN_STATUSES:
            continue
        client.table("replacement_offers").update({"status": "superseded"}) \
            .eq("facility_id", facility_id).eq("id", other["id"]).execute()
        notify.push(client, facility_id, staff_id=other["offered_staff_id"],
                    event_type="replacement_offer_closed",
                    title="That shift has been covered",
                    related_type="replacement_offer", related_id=other["id"])

    audit.record(client, facility_id=facility_id, action="update",
                 entity_table="replacement_offers", entity_id=offer_id,
                 before={"status": "accepted"},
                 after={"status": "approved",
                        "incident_id": row["incident_id"],
                        "replacement_staff_id": row["offered_staff_id"]},
                 actor_profile_id=profile_id)
    return {"offer": approved, **result}


def withdraw(client, facility_id: str, offer_id: str, *,
             profile_id: str | None = None) -> dict:
    """Pull an offer back before it has been committed."""
    row = _offer(client, facility_id, offer_id)
    if row["status"] not in OPEN_STATUSES:
        raise ValueError(f"this offer is {row['status']} and cannot be withdrawn")
    updated = (client.table("replacement_offers").update({"status": "withdrawn"})
               .eq("facility_id", facility_id).eq("id", offer_id).execute().data[0])
    notify.push(client, facility_id, staff_id=row["offered_staff_id"],
                event_type="replacement_offer_closed",
                title="That cover request has been withdrawn",
                related_type="replacement_offer", related_id=offer_id)
    return updated


def list_offers(client, facility_id: str, *, incident_id: str | None = None,
                staff_id: str | None = None, status: str | None = None,
                limit: int = 50) -> list[dict]:
    """The manager's view of one incident, or one staff member's own inbox."""
    q = client.table("replacement_offers").select("*").eq("facility_id", facility_id)
    if incident_id:
        q = q.eq("incident_id", incident_id)
    if staff_id:
        q = q.eq("offered_staff_id", staff_id)
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).limit(limit).execute().data
