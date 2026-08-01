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
