"""Focused Phase 5 KPI fixtures."""
from __future__ import annotations

from emma_core.services import kpi, roi

from tests.test_optimize_service import build_store


def test_external_workforce_deduplicates_linked_agency_purchase():
    store = build_store()
    store.data["roster_versions"][0]["status"] = "published"
    assignment = store.data["shift_assignments"][0]
    assignment["is_agency"] = True
    store.data["agency_assignments"] = [{
        "id": "purchase-1",
        "facility_id": "f1",
        "shift_id": assignment["shift_id"],
        "shift_assignment_id": assignment["id"],
        "date": "2026-07-01",
        "role": assignment["role"],
        "cost": 1231,
    }]

    result = kpi.external_workforce(store, "f1", "p1")

    assert result["agency_shifts"] == 1
    assert result["agency_cost"] == 1231
    assert result["external_shifts"] == 1
    assert result["total_shifts"] == len(store.data["shift_assignments"])


def test_external_workforce_excludes_linked_purchase_from_other_draft():
    store = build_store()
    store.data["roster_versions"][0]["status"] = "published"
    store.data["roster_versions"].append({
        "id": "other-draft",
        "facility_id": "f1",
        "period_id": "p1",
        "version_type": "A",
        "status": "draft",
        "created_at": "2026-07-21T00:00:00",
    })
    store.data["shifts"].append({
        "id": "other-shift",
        "facility_id": "f1",
        "roster_version_id": "other-draft",
        "date": "2026-07-01",
        "shift_type": "A",
        "is_working": True,
    })
    store.data["agency_assignments"] = [{
        "id": "other-purchase",
        "facility_id": "f1",
        "shift_id": "other-shift",
        "shift_assignment_id": "other-cell",
        "date": "2026-07-01",
        "role": "CW",
        "cost": 957,
    }]

    result = kpi.external_workforce(store, "f1", "p1")

    assert result["agency_shifts"] == 0
    assert result["agency_cost"] == 0


def test_roi_spend_excludes_generated_draft_purchase():
    store = build_store()
    store.data["agency_assignments"] = [
        {
            "id": "draft-purchase",
            "facility_id": "f1",
            "shift_id": "rnA0",
            "date": "2026-07-01",
            "role": "RN",
            "hours": 8,
            "cost": 1231,
        },
        {
            "id": "actual-unlinked-purchase",
            "facility_id": "f1",
            "shift_id": None,
            "date": "2026-07-01",
            "role": "CW",
            "hours": 8,
            "cost": 957,
        },
    ]

    result = roi._agency_spend(store, "f1", "2026-07-01", "2026-07-31")

    assert result["shifts"] == 1
    assert result["monthly_cost"] == 957


# ── 3.1 · the KPI strip's "Completion" card ─────────────────────────────────
# Cherry settled the ambiguity on 2 Aug 2026: task completion, "% of assigned
# tasks marked done per shift" - not roster completion, not the compliance pass
# rate.

def _store_with_tasks(statuses: list[str]):
    store = build_store()
    store.data["roster_versions"][0]["status"] = "published"
    assignment = store.data["shift_assignments"][0]
    store.data["task_assignments"] = [
        {"id": f"t{i}", "facility_id": "f1",
         "shift_assignment_id": assignment["id"], "task_status": status}
        for i, status in enumerate(statuses)
    ]
    return store


def test_task_completion_is_the_share_of_assigned_tasks_ticked_off():
    result = kpi.task_completion(_store_with_tasks(
        ["done", "done", "done", "pending"]), "f1", "p1")
    assert (result["assigned"], result["done"]) == (4, 3)
    assert result["completion_pct"] == 75.0


def test_an_untouched_task_counts_against_completion():
    """The denominator is every assigned task, not just the ones somebody
    opened - a medication round nobody looked at is not done."""
    result = kpi.task_completion(_store_with_tasks(["pending", "pending"]), "f1", "p1")
    assert result["completion_pct"] == 0.0 and result["done"] == 0


def test_exceptions_are_reported_separately_rather_than_counted_as_done():
    """A task refused for a stated clinical reason is a different failure from
    one silently skipped; one percentage would hide which a home is looking at."""
    result = kpi.task_completion(_store_with_tasks(
        ["done", "exception", "skipped", "done"]), "f1", "p1")
    assert result["exceptions"] == 1
    assert result["completion_pct"] == 50.0


def test_a_roster_with_no_task_codes_reports_no_percentage_rather_than_zero():
    """A home that rosters nothing to tick has not failed to tick it, and a red
    0% would say it did."""
    result = kpi.task_completion(_store_with_tasks([]), "f1", "p1")
    assert result["completion_pct"] is None
    assert (result["assigned"], result["done"]) == (0, 0)


def test_task_completion_breaks_down_per_shift_type():
    store = _store_with_tasks(["done", "pending"])
    other = store.data["shift_assignments"][1]          # a P shift, not the A above
    store.data["task_assignments"].append(
        {"id": "t9", "facility_id": "f1",
         "shift_assignment_id": other["id"], "task_status": "done"})
    by_shift = {s["shift_type"]: s
                for s in kpi.task_completion(store, "f1", "p1")["by_shift"]}
    assert by_shift["A"]["completion_pct"] == 50.0
    assert by_shift["P"]["completion_pct"] == 100.0


def test_task_completion_is_part_of_the_one_call_overview():
    """The strip reads GET /kpi/overview, so a KPI missing from that payload is
    invisible however correctly it computes."""
    assert "task_completion" in kpi.__all__
