"""Phase 0 records and the submission evidence checklist (spec 0.1 / 0.2 / 1.6).

Three registers that exist so the paperwork around the platform is queryable
rather than only written down:

``architecture_decisions``
    Why this database, this hosting, this rule engine - and what the decision has
    to keep satisfying. Cross-facility: the platform makes this choice once.
``project_scope``
    What the 7-week MVP includes and what is deferred, keyed to the delivery
    plan's own phase names so a scope question has one answer.
``evidence_items``
    One row per item in the client/government submission pack, each with an owner,
    a test method, a sample output and whether an external qualified reviewer is
    required.

The wording constraints in the delivery plan are load-bearing and are enforced
here rather than left to a document: nothing in this module states that deletion
is unconditional, fixes an AI vendor, claims automatic critical-infrastructure
status, or promises TLS 1.3 only. `EVIDENCE_CAVEATS` carries that language and is
returned with the checklist so an export cannot lose it.
"""
from __future__ import annotations

from ._common import now_iso

EVIDENCE_STATUSES = ("pending", "pass", "fail", "not_applicable")

# Returned with every evidence read and embedded in the evidence report, so the
# qualifications travel with the claims.
EVIDENCE_CAVEATS: tuple[str, ...] = (
    "Deletion requests are handled per PDPO, subject to legal, HR, SWD-audit and "
    "statutory record-keeping obligations; deletion is not unconditional.",
    "A 7-year audit retention period is proposed and requires client/legal "
    "confirmation.",
    "AI features run through an approved provider behind a controlled API "
    "gateway; no vendor is fixed at this stage.",
    "Transport security is TLS 1.2 minimum, TLS 1.3 where supported.",
    "SRAA or third-party security review is available if required; Emma AI is not "
    "asserted to be critical infrastructure.",
    "These are the engineering team's technical test results. Formal legal or "
    "security certification requires an external qualified reviewer.",
)


# ── 0.1 architecture decisions ───────────────────────────────────────────────
def list_decisions(client, *, status: str | None = None) -> list[dict]:
    # SQL: select * from architecture_decisions [where status = :status]
    #      order by code
    query = client.table("architecture_decisions").select("*")
    if status:
        query = query.eq("status", status)
    return query.order("code").execute().data


def get_decision(client, code: str) -> dict | None:
    # SQL: select * from architecture_decisions where code = :code
    rows = (client.table("architecture_decisions").select("*")
            .eq("code", code).execute().data)
    return rows[0] if rows else None


# ── 0.2 scope lock ───────────────────────────────────────────────────────────
def list_scope(client, *, scope: str | None = None) -> list[dict]:
    # SQL: select * from project_scope [where scope = :scope] order by item_code
    query = client.table("project_scope").select("*")
    if scope:
        query = query.eq("scope", scope)
    return query.order("item_code").execute().data


def scope_summary(client) -> dict:
    """MVP versus deferred, grouped by delivery phase."""
    rows = list_scope(client)
    by_phase: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        bucket = by_phase.setdefault(row["phase"], {"mvp": [], "deferred": []})
        bucket[row["scope"]].append(row["item_code"])
    return {
        "mvp_items": sum(1 for r in rows if r["scope"] == "mvp"),
        "deferred_items": sum(1 for r in rows if r["scope"] == "deferred"),
        "by_phase": {phase: {k: sorted(v) for k, v in buckets.items()}
                     for phase, buckets in sorted(by_phase.items())},
    }


# ── 1.6 evidence checklist ───────────────────────────────────────────────────
def list_evidence(client, facility_id: str, *, category: str | None = None
                  ) -> list[dict]:
    # SQL: select * from evidence_items
    #      where (facility_id = :facility_id or facility_id is null)
    #        [and category = :category]
    #      order by sort_order, code
    query = (client.table("evidence_items").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null"))
    if category:
        query = query.eq("category", category)
    return query.order("sort_order").order("code").execute().data


def evidence_checklist(client, facility_id: str) -> dict:
    """The checklist plus its counts and the caveats that must accompany it."""
    items = list_evidence(client, facility_id)
    counts: dict[str, int] = {status: 0 for status in EVIDENCE_STATUSES}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "items": items,
        "counts": counts,
        "external_review_required": [i["code"] for i in items
                                     if i["external_review_required"]],
        "caveats": list(EVIDENCE_CAVEATS),
        "generated_at": now_iso(),
    }


def set_evidence_status(client, facility_id: str, code: str, *, status: str,
                        sample_output: str | None = None,
                        notes: str | None = None,
                        checked_on: str | None = None) -> dict:
    """Record the result of one evidence check.

    Only facility-scoped rows are writable through the API; the shared
    platform-wide controls are owned by a migration so one tenant cannot mark
    another's evidence as passed.
    """
    if status not in EVIDENCE_STATUSES:
        raise ValueError(f"status must be one of {', '.join(EVIDENCE_STATUSES)}")
    # SQL: select id from evidence_items
    #      where facility_id = :facility_id and code = :code
    rows = (client.table("evidence_items").select("id")
            .eq("facility_id", facility_id).eq("code", code).execute().data)
    if not rows:
        raise ValueError(f"no facility-scoped evidence item {code!r}")
    patch = {"status": status, "updated_at": now_iso()}
    if sample_output is not None:
        patch["sample_output"] = sample_output
    if notes is not None:
        patch["notes"] = notes
    if checked_on is not None:
        patch["checked_on"] = checked_on
    # SQL: update evidence_items set ... where id = :id returning *
    return (client.table("evidence_items").update(patch)
            .eq("id", rows[0]["id"]).execute().data[0])
