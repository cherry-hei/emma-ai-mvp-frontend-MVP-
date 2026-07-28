"""Leave / duty requests and the Approval Centre workflow (spec 4.2).

Three request categories map to the Approval page's sub-tabs:
    al    annual + special leave       (AL, special, marriage, …)
    duty  day-off / shift requests     (DO, duty_request)
    sick  sick, urgent, lateness       (SL, DSL, urgent, late)

A `sick` request for an imminent shift is also an operational emergency, so
creating one opens an sl_incident (spec 4.3) — that is what puts the case on the
Alert centre and into the A2 ROI count.
"""
from __future__ import annotations

from datetime import date as Date

from . import notifications as notify
from ._common import iso, month_bounds, now_iso, staff_brief, staff_by_id

# leave_type -> category, so callers can post either and stay consistent.
TYPE_CATEGORY = {
    "AL": "al", "special": "al", "marriage": "al", "maternity": "al", "unpaid": "al",
    "DO": "duty", "duty_request": "duty", "shift_swap": "duty",
    "SL": "sick", "DSL": "sick", "urgent": "sick", "late": "sick",
}
INCIDENT_TYPES = {"SL", "DSL", "urgent", "late"}   # also raise an sl_incident

PENDING_STATES = ("pending", "reviewed")
DECIDED_STATES = ("approved", "rejected")


def category_for(leave_type: str) -> str:
    cat = TYPE_CATEGORY.get(leave_type)
    if not cat:
        raise ValueError(f"unknown leave_type {leave_type!r}")
    return cat


def _row_out(row: dict, staff: dict[str, dict]) -> dict:
    return {
        **staff_brief(staff.get(row["staff_id"])),
        "id": row["id"],
        "category": row["category"],
        "leave_type": row["leave_type"],
        "date_start": row["date_start"],
        "date_end": row["date_end"],
        "requested_shift_type": row.get("requested_shift_type"),
        "reason": row.get("reason"),
        "remark": row.get("remark"),
        "document_url": row.get("document_url"),
        "status": row["status"],
        "reviewed": bool(row.get("reviewed_at")),
        "decided_at": row.get("decided_at"),
        "decision_note": row.get("decision_note"),
        "created_at": row.get("created_at"),
    }


def list_requests(client, facility_id: str, *, group: str | None = None,
                  category: str | None = None, search: str | None = None,
                  unit_id: str | None = None, date_from: Date | None = None,
                  date_to: Date | None = None, staff_id: str | None = None) -> list[dict]:
    """`group` is the Approval page's main tab: 'pending' (open) or 'approved' (decided)."""
    # SQL: select * from leave_requests
    #      where facility_id = :facility_id
    #        [and status = any('{pending,reviewed}')]    -- group = 'pending'
    #        [and status = any('{approved,rejected}')]   -- group = 'approved'
    #        [and category = :category]                  -- when category is given
    #        [and staff_id = :staff_id]                  -- when staff_id is given
    #        [and date_end   >= :date_from]              -- overlap, not containment
    #        [and date_start <= :date_to]
    #      order by created_at desc
    # `search` and `unit_id` are NOT pushed down — both need the staff row, so they
    # are applied in the Python loop below against staff_by_id().
    q = client.table("leave_requests").select("*").eq("facility_id", facility_id)
    if group == "pending":
        q = q.in_("status", list(PENDING_STATES))
    elif group == "approved":
        q = q.in_("status", list(DECIDED_STATES))
    if category:
        q = q.eq("category", category)
    if staff_id:
        q = q.eq("staff_id", staff_id)
    if date_from:
        q = q.gte("date_end", str(date_from))       # overlap, not containment
    if date_to:
        q = q.lte("date_start", str(date_to))
    rows = q.order("created_at", desc=True).execute().data

    staff = staff_by_id(client, facility_id)
    needle = search.lower().strip() if search else None
    out = []
    for r in rows:
        st = staff.get(r["staff_id"]) or {}
        if unit_id and st.get("primary_unit_id") != unit_id:
            continue
        if needle:
            hay = f'{st.get("name") or ""} {st.get("name_en") or ""}'.lower()
            if needle not in hay:
                continue
        out.append(_row_out(r, staff))
    return out


def create_request(client, facility_id: str, *, staff_id: str, leave_type: str,
                   date_start: Date, date_end: Date, reason: str | None = None,
                   remark: str | None = None, requested_shift_type: str | None = None,
                   document_url: str | None = None) -> dict:
    if date_end < date_start:
        raise ValueError("date_end is before date_start")
    category = category_for(leave_type)
    # SQL: insert into leave_requests
    #        (facility_id, staff_id, category, leave_type, date_start, date_end,
    #         requested_shift_type, reason, remark, document_url, status)
    #      values (:facility_id, :staff_id, :category, :leave_type, :date_start,
    #              :date_end, :requested_shift_type, :reason, :remark,
    #              :document_url, 'pending')
    #      returning *
    row = client.table("leave_requests").insert({
        "facility_id": facility_id, "staff_id": staff_id, "category": category,
        "leave_type": leave_type, "date_start": str(date_start), "date_end": str(date_end),
        "requested_shift_type": requested_shift_type, "reason": reason, "remark": remark,
        "document_url": document_url, "status": "pending",
    }).execute().data[0]

    if leave_type in INCIDENT_TYPES:
        from . import incidents                       # local: incidents imports leave helpers
        incidents.open_incident(
            client, facility_id, staff_id=staff_id, incident_type=leave_type,
            on_date=date_start, reason=reason, leave_request_id=row["id"],
        )
    return row


def decide(client, facility_id: str, request_id: str, *, decision: str,
           profile_id: str | None, note: str | None = None) -> dict:
    """decision: 'approve' | 'reject' | 'review'. 'review' only flags the request as
    read by the superintendent; it stays in the pending queue."""
    # SQL: select * from leave_requests
    #      where facility_id = :facility_id and id = :request_id
    rows = (client.table("leave_requests").select("*")
            .eq("facility_id", facility_id).eq("id", request_id).execute().data)
    if not rows:
        raise ValueError("leave request not found")
    current = rows[0]

    if decision == "review":
        patch = {"status": "reviewed", "reviewed_at": now_iso()}
    elif decision in ("approve", "reject"):
        patch = {
            "status": "approved" if decision == "approve" else "rejected",
            "reviewed_at": current.get("reviewed_at") or now_iso(),
            "decided_by": profile_id, "decided_at": now_iso(), "decision_note": note,
        }
    else:
        raise ValueError(f"unknown decision {decision!r}")

    # SQL: update leave_requests
    #      set <the keys of `patch` above>   -- 'review': status, reviewed_at
    #                                        -- approve/reject: status, reviewed_at,
    #                                        --   decided_by, decided_at, decision_note
    #      where facility_id = :facility_id and id = :request_id
    #      returning *
    row = (client.table("leave_requests").update(patch)
           .eq("facility_id", facility_id).eq("id", request_id).execute().data[0])

    if decision in ("approve", "reject"):
        verdict = "approved" if decision == "approve" else "rejected"
        notify.push(
            client, facility_id, staff_id=row["staff_id"], event_type="leave_decided",
            title=f'{row["leave_type"]} request {verdict}',
            body=f'{iso(row["date_start"])} – {iso(row["date_end"])}'
                 + (f' · {note}' if note else ""),
            related_type="leave_request", related_id=row["id"],
        )
    return row


def stats(client, facility_id: str, on: Date | None = None) -> dict:
    """Approval Centre header numbers for the calendar month containing `on`."""
    start, end = month_bounds(on)
    # SQL: select status, decided_at, created_at from leave_requests
    #      where facility_id = :facility_id
    #        and created_at >= :month_start::date
    #        and created_at <= (:month_end::date + time '23:59:59')
    # The four counters are tallied in Python rather than as
    # `count(*) filter (where status = ...)`, so one fetch serves all of them.
    rows = (client.table("leave_requests").select("status,decided_at,created_at")
            .eq("facility_id", facility_id)
            .gte("created_at", f"{start}T00:00:00Z").lte("created_at", f"{end}T23:59:59Z")
            .execute().data)
    decided = [r for r in rows if r["status"] in DECIDED_STATES]
    approved = [r for r in decided if r["status"] == "approved"]
    pending = [r for r in rows if r["status"] in PENDING_STATES]
    return {
        "month_start": start, "month_end": end,
        "total_actions": len(rows),
        "decided_count": len(decided),
        "approved_count": len(approved),
        "pending_count": len(pending),
        "approval_rate": round(len(approved) / len(decided) * 100) if decided else 0,
    }


def approved_leave_dates(client, facility_id: str, start: Date, end: Date) -> set[tuple[str, str]]:
    """{(staff_id, 'YYYY-MM-DD')} for approved leave overlapping [start, end] — the
    availability filter used by roster edits and replacement suggestions."""
    # SQL: select staff_id, date_start, date_end from leave_requests
    #      where facility_id = :facility_id
    #        and status = 'approved'
    #        and date_start <= :end and date_end >= :start   -- range overlap
    # The per-day expansion into (staff_id, date) pairs happens in Python below;
    # in SQL it would be a `generate_series(date_start, date_end, '1 day')` join.
    rows = (client.table("leave_requests").select("staff_id,date_start,date_end")
            .eq("facility_id", facility_id).eq("status", "approved")
            .lte("date_start", str(end)).gte("date_end", str(start)).execute().data)
    out: set[tuple[str, str]] = set()
    for r in rows:
        d, last = Date.fromisoformat(iso(r["date_start"])), Date.fromisoformat(iso(r["date_end"]))
        while d <= last:
            if start <= d <= end:
                out.add((r["staff_id"], d.isoformat()))
            d = Date.fromordinal(d.toordinal() + 1)
    return out
