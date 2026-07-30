"""Leave / duty requests and the Approval Centre workflow (spec 4.2).

Three request categories map to the Approval page's sub-tabs:
    al    annual + special leave       (AL, special, marriage, …)
    duty  day-off / shift requests     (DO, duty_request)
    sick  sick, urgent, lateness       (SL, DSL, urgent, late)

A `sick` request for an imminent shift is also an operational emergency, so
creating one opens an sl_incident (spec 4.3) - that is what puts the case on the
Alert centre and into the A2 ROI count.
"""
from __future__ import annotations

from datetime import date as Date

from . import notifications as notify
from . import validation
from ._common import iso, month_bounds, now_iso, staff_brief, staff_by_id

# leave_type -> category, so callers can post either and stay consistent.
TYPE_CATEGORY = {
    "AL": "al", "PH": "al", "CL": "al", "medical_fu": "al",
    "special": "al", "marriage": "al", "maternity": "al", "unpaid": "al",
    "DO": "duty", "duty_request": "duty", "shift_swap": "duty",
    "SL": "sick", "DSL": "sick", "urgent": "sick", "late": "sick",
}
INCIDENT_TYPES = {"SL", "DSL", "urgent", "late"}   # also raise an sl_incident
NIGHT_SHIFT_TYPES = {"AN", "N", "7P"}

PENDING_STATES = ("pending", "reviewed")
DECIDED_STATES = ("approved", "rejected")


def category_for(leave_type: str) -> str:
    cat = TYPE_CATEGORY.get(leave_type)
    if not cat:
        raise ValueError(f"unknown leave_type {leave_type!r}")
    return cat


def _effective_leave_policy(
    rows: list[dict],
    facility_id: str,
    on_date: Date,
) -> tuple[dict, str]:
    """Select the policy frozen at the target roster-period boundary."""
    candidates = [
        row for row in rows
        if row.get("rule_code") == "leave_rules"
        and row.get("active", True)
        and row.get("facility_id") in (None, facility_id)
        and (
            not row.get("effective_from")
            or Date.fromisoformat(iso(row["effective_from"])) <= on_date
        )
        and (
            not row.get("effective_to")
            or Date.fromisoformat(iso(row["effective_to"])) >= on_date
        )
    ]
    candidates.sort(
        key=lambda row: (
            row.get("facility_id") == facility_id,
            int(row.get("config_version") or 1),
            str(row.get("effective_from") or ""),
        ),
        reverse=True,
    )
    policy = dict(validation.DEFAULT_LEAVE_POLICY)
    if not candidates:
        return policy, "hard"
    policy.update(candidates[0].get("config_json") or {})
    return policy, str(candidates[0].get("severity") or "hard")


def _policy_context(
    client,
    facility_id: str,
    *,
    staff_id: str,
    date_start: Date,
    date_end: Date,
) -> dict:
    """Load the bounded DB evidence used by the pure Phase 5 leave rules."""
    facilities = (
        client.table("facilities").select("*")
        .eq("id", facility_id).execute().data
    )
    if not facilities:
        raise ValueError("facility not found")

    facility_staff = (
        client.table("staff").select("*")
        .eq("facility_id", facility_id).execute().data
    )
    staff = next((row for row in facility_staff if row["id"] == staff_id), None)
    if staff is None:
        raise ValueError("staff member not found")
    active_staff = [
        row for row in facility_staff
        if row.get("status", "active") == "active"
    ]

    month_start, _ = month_bounds(date_start)
    _, month_end = month_bounds(date_end)
    existing_requests = (
        client.table("leave_requests").select("*")
        .eq("facility_id", facility_id)
        .lte("date_start", month_end).gte("date_end", month_start)
        .execute().data
    )
    calendar_days = (
        client.table("calendar_days").select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .gte("date", str(month_start)).lte("date", str(month_end))
        .execute().data
    )

    assignment_rows = (
        client.table("shift_assignments")
        .select(
            "status,shift:shifts(date,shift_type,is_working,"
            "version:roster_versions(version_type,status))"
        )
        .eq("facility_id", facility_id).eq("staff_id", staff_id)
        .execute().data
    )
    assigned_night_shifts: dict[Date, str] = {}
    for assignment in assignment_rows:
        shift = assignment.get("shift") or {}
        version = shift.get("version") or {}
        if assignment.get("status") == "cancelled" or not shift.get("is_working"):
            continue
        is_operative = (
            version.get("status") == "published"
            or (
                version.get("version_type") == "manual"
                and version.get("status") == "draft"
            )
        )
        if not is_operative:
            continue
        if (
            shift.get("shift_type") not in NIGHT_SHIFT_TYPES
            or not shift.get("date")
        ):
            continue
        shift_date = Date.fromisoformat(iso(shift.get("date")))
        if date_start <= shift_date <= date_end:
            assigned_night_shifts[shift_date] = str(
                shift.get("shift_type") or "").upper()

    periods = (
        client.table("roster_periods").select("id,period_start,period_end")
        .eq("facility_id", facility_id)
        .lte("period_start", str(date_end)).gte("period_end", str(date_start))
        .execute().data
    )
    balances = []
    for period in periods:
        period_balances = (
            client.table("leave_balances").select("*")
            .eq("facility_id", facility_id).eq("staff_id", staff_id)
            .eq("period_id", period["id"])
            .execute().data
        )
        balances.extend({
            **row,
            "period_start": period["period_start"],
            "period_end": period["period_end"],
        } for row in period_balances)

    rule_rows = (
        client.table("rule_definitions").select("*")
        .eq("rule_code", "leave_rules").execute().data
    )
    leave_policy, leave_policy_severity = _effective_leave_policy(
        rule_rows,
        facility_id,
        min(
            (
                Date.fromisoformat(iso(period["period_start"]))
                for period in periods
            ),
            default=date_start,
        ),
    )
    return {
        "facility": facilities[0],
        "staff": staff,
        "active_staff": active_staff,
        "existing_requests": existing_requests,
        "calendar_days": calendar_days,
        "assigned_night_shifts": assigned_night_shifts,
        "balances": balances,
        "balance_periods": periods,
        "leave_policy": leave_policy,
        "leave_policy_severity": leave_policy_severity,
    }


def _evaluate_request_policy(
    client,
    facility_id: str,
    request: dict,
    *,
    submitted_on: Date,
) -> tuple[str, str, dict]:
    start = Date.fromisoformat(iso(request["date_start"]))
    end = Date.fromisoformat(iso(request["date_end"]))
    context = _policy_context(
        client,
        facility_id,
        staff_id=request["staff_id"],
        date_start=start,
        date_end=end,
    )
    priority, priority_reason = validation.leave_priority(
        request["leave_type"], request.get("reason"))
    issues = validation.leave_request_policy_issues(
        request=request,
        staff=context["staff"],
        facility=context["facility"],
        existing_requests=context["existing_requests"],
        active_staff=context["active_staff"],
        calendar_days=context["calendar_days"],
        assigned_night_shifts=context["assigned_night_shifts"],
        submitted_on=submitted_on,
        policy=context["leave_policy"],
        policy_severity=context["leave_policy_severity"],
    )
    issues.extend(validation.leave_balance_issues(
        request=request,
        balances=context["balances"],
        periods=context["balance_periods"],
    ))
    policy_result = {
        "passes": not any(row.get("severity") == "hard" for row in issues),
        "issues": issues,
        "priority_weight": validation.leave_priority_weight(
            request["leave_type"],
            request.get("reason"),
        ),
    }
    prior_policy = request.get("policy_result_json") or {}
    if prior_policy.get("ballot_approved"):
        policy_result.update({
            key: prior_policy[key]
            for key in (
                "ballot_approved",
                "ballot_decided_by",
                "ballot_decided_at",
            )
            if key in prior_policy
        })
    return priority, priority_reason, policy_result


def _hard_issue_codes(policy_result: dict) -> list[str]:
    return [
        str(row.get("code") or "leave_policy")
        for row in policy_result.get("issues") or []
        if row.get("severity") == "hard"
    ]


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
        "priority": row.get("priority", "normal"),
        "priority_reason": row.get("priority_reason"),
        "policy_result_json": row.get("policy_result_json") or {},
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
    # `search` and `unit_id` are NOT pushed down - both need the staff row, so they
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
    positive_duty = leave_type in {"duty_request", "shift_swap"}
    if positive_duty and not requested_shift_type:
        raise ValueError(
            "requested_shift_type is required for a duty request or shift swap"
        )
    if not positive_duty and requested_shift_type:
        raise ValueError(
            "requested_shift_type is only valid for a duty request or shift swap"
        )
    category = category_for(leave_type)
    request = {
        "facility_id": facility_id,
        "staff_id": staff_id,
        "category": category,
        "leave_type": leave_type,
        "date_start": str(date_start),
        "date_end": str(date_end),
        "requested_shift_type": requested_shift_type,
        "reason": reason,
        "remark": remark,
        "document_url": document_url,
        "status": "pending",
    }
    priority, priority_reason, policy_result = _evaluate_request_policy(
        client,
        facility_id,
        request,
        submitted_on=Date.today(),
    )
    # SQL: insert into leave_requests
    #        (facility_id, staff_id, category, leave_type, date_start, date_end,
    #         requested_shift_type, reason, remark, document_url, status,
    #         priority, priority_reason, policy_result_json)
    #      values (:facility_id, :staff_id, :category, :leave_type, :date_start,
    #              :date_end, :requested_shift_type, :reason, :remark,
    #              :document_url, 'pending', :priority, :priority_reason,
    #              :policy_result_json)
    #      returning *
    row = client.table("leave_requests").insert({
        **request,
        "priority": priority,
        "priority_reason": priority_reason,
        "policy_result_json": policy_result,
    }).execute().data[0]

    if leave_type in INCIDENT_TYPES:
        from . import incidents                       # local: incidents imports leave helpers
        incidents.open_incident(
            client, facility_id, staff_id=staff_id, incident_type=leave_type,
            on_date=date_start, reason=reason, leave_request_id=row["id"],
        )
    return row


def decide(client, facility_id: str, request_id: str, *, decision: str,
           profile_id: str | None, note: str | None = None,
           ballot_approved: bool | None = None) -> dict:
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

    if decision == "approve":
        if ballot_approved is not None:
            current = {
                **current,
                "policy_result_json": {
                    **(current.get("policy_result_json") or {}),
                    "ballot_approved": ballot_approved,
                    "ballot_decided_by": profile_id,
                    "ballot_decided_at": now_iso(),
                },
            }
        submitted_on = Date.fromisoformat(
            iso(current.get("created_at") or Date.today()))
        priority, priority_reason, policy_result = _evaluate_request_policy(
            client,
            facility_id,
            current,
            submitted_on=submitted_on,
        )
        policy_patch = {
            "priority": priority,
            "priority_reason": priority_reason,
            "policy_result_json": policy_result,
        }
        hard_codes = _hard_issue_codes(policy_result)
        if hard_codes:
            # Persist the current evidence while leaving the workflow state open.
            (client.table("leave_requests").update(policy_patch)
             .eq("facility_id", facility_id).eq("id", request_id).execute())
            raise ValueError(
                "leave request cannot be approved: " + ", ".join(hard_codes))
        patch.update(policy_patch)

    # SQL: update leave_requests
    #      set <the keys of `patch` above>   -- 'review': status, reviewed_at
    #                                        -- approve/reject: status, reviewed_at,
    #                                        --   decided_by, decided_at, decision_note,
    #                                        --   and current Phase 5 policy evidence
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
    """{(staff_id, 'YYYY-MM-DD')} for approved leave overlapping [start, end] - the
    availability filter used by roster edits and replacement suggestions."""
    # SQL: select staff_id, date_start, date_end from leave_requests
    #      where facility_id = :facility_id
    #        and status = 'approved'
    #        and date_start <= :end and date_end >= :start   -- range overlap
    # The per-day expansion into (staff_id, date) pairs happens in Python below;
    # in SQL it would be a `generate_series(date_start, date_end, '1 day')` join.
    rows = (client.table("leave_requests").select(
                "staff_id,date_start,date_end,leave_type"
            )
            .eq("facility_id", facility_id).eq("status", "approved")
            .lte("date_start", str(end)).gte("date_end", str(start)).execute().data)
    out: set[tuple[str, str]] = set()
    for r in rows:
        if r.get("leave_type") in {"duty_request", "shift_swap"}:
            continue
        d, last = Date.fromisoformat(iso(r["date_start"])), Date.fromisoformat(iso(r["date_end"]))
        while d <= last:
            if start <= d <= end:
                out.add((r["staff_id"], d.isoformat()))
            d = Date.fromordinal(d.toordinal() + 1)
    return out
