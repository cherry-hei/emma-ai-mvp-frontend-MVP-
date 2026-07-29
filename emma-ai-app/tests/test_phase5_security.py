from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import AuthCtx
from api.routers.optimize import _authorize_optimize
from emma_core.models import OptimizeRequest, Profile, SolverLimitsModel
from emma_core.services import optimize, roster
from emma_core.solver import DemandSlot, SolverInputs, StaffInput, WorkPatternInput

from tests.test_optimize_service import FakeSupabase, build_store


def _ctx(client, *, role: str = "scheduler") -> AuthCtx:
    return AuthCtx(
        token="test-token",
        client=client,
        profile=Profile(
            id="profile-1",
            facility_id="f1",
            role=role,
        ),
    )


def test_optimize_authorization_rejects_staff_and_overwrites_identity():
    store = build_store()
    denied = OptimizeRequest(
        facility_id="spoofed",
        period_id="p1",
        created_by="spoofed-author",
    )
    with pytest.raises(HTTPException) as exc:
        _authorize_optimize(denied, _ctx(store, role="staff"))
    assert exc.value.status_code == 403

    allowed = OptimizeRequest(
        facility_id="spoofed",
        period_id="p1",
        created_by="spoofed-author",
    )
    _authorize_optimize(allowed, _ctx(store))
    assert allowed.facility_id == "f1"
    assert allowed.created_by == "profile-1"


def test_source_version_must_belong_to_requested_period_at_both_boundaries():
    store = build_store()
    store.data["roster_periods"].append({
        "id": "p2",
        "facility_id": "f1",
        "period_start": "2026-08-01",
        "period_end": "2026-08-28",
    })
    store.data["roster_versions"].append({
        "id": "other-period-version",
        "facility_id": "f1",
        "period_id": "p2",
        "version_type": "manual",
        "status": "draft",
    })
    request = OptimizeRequest(
        facility_id="f1",
        period_id="p1",
        source_version_id="other-period-version",
    )

    with pytest.raises(HTTPException) as exc:
        _authorize_optimize(request, _ctx(store))
    assert exc.value.status_code == 404

    with pytest.raises(ValueError, match="no source"):
        optimize.load_inputs(
            store,
            "f1",
            "p1",
            source_version_id="other-period-version",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_seconds", 0),
        ("max_seconds", 121),
        ("workers", 0),
        ("workers", 33),
    ],
)
def test_solver_resource_limits_are_bounded(field, value):
    with pytest.raises(ValidationError):
        SolverLimitsModel(**{field: value})


def test_leave_loader_uses_leave_type_not_stray_requested_shift():
    store = build_store()
    store.data["leave_requests"] = [
        {
            "id": "approved-leave",
            "facility_id": "f1",
            "staff_id": "cw1",
            "leave_type": "CL",
            "date_start": "2026-07-01",
            "date_end": "2026-07-01",
            "requested_shift_type": "A",
            "status": "approved",
        },
        {
            "id": "reviewed-duty",
            "facility_id": "f1",
            "staff_id": "cw2",
            "leave_type": "duty_request",
            "date_start": "2026-07-01",
            "date_end": "2026-07-01",
            "requested_shift_type": "P",
            "status": "reviewed",
        },
        {
            "id": "pending-swap",
            "facility_id": "f1",
            "staff_id": "cw2",
            "leave_type": "shift_swap",
            "date_start": "2026-07-02",
            "date_end": "2026-07-02",
            "requested_shift_type": "A",
            "status": "pending",
        },
        {
            "id": "pending-leave",
            "facility_id": "f1",
            "staff_id": "cw1",
            "leave_type": "AL",
            "date_start": "2026-07-02",
            "date_end": "2026-07-02",
            "requested_shift_type": "N",
            "status": "pending",
        },
    ]

    loaded = optimize.load_inputs(store, "f1", "p1")

    assert ("cw1", loaded.period_start) in loaded.leave_unavailable
    by_key = {
        (preference.staff_id, preference.date): preference
        for preference in loaded.preferences
    }
    duty = by_key[("cw2", loaded.period_start)]
    assert duty.prefer_working and duty.shift_type == "P"
    swap = by_key[("cw2", loaded.period_end)]
    assert swap.prefer_working and swap.shift_type == "A"
    leave_preference = by_key[("cw1", loaded.period_end)]
    assert not leave_preference.prefer_working
    assert leave_preference.shift_type is None


def test_part_time_policy_maps_to_solver_work_pattern():
    store = build_store()
    store.data["staff"][1]["employment_type"] = "local_pt"
    store.data["rule_definitions"] = [{
        "id": "agency-policy",
        "facility_id": "f1",
        "rule_code": "agency_limits",
        "active": True,
        "config_version": 1,
        "config_json": {
            "part_time_policy": {
                "employment_types": ["local_pt"],
                "required_start": "09:00",
                "required_end": "17:48",
                "allowed_weekdays": [0, 1, 2, 3, 4, 5],
                "weekly_work_days": {"min": 5, "max": 6},
                "fortnightly_work_days": {"min": 11, "max": 11},
                "saturday_requires_weekday_cl": True,
            },
        },
    }]

    loaded = optimize.load_inputs(store, "f1", "p1")
    pattern = next(
        staff.work_pattern for staff in loaded.staff if staff.id == "cw1"
    )

    assert pattern.required_shift_window == (9 * 60, 17 * 60 + 48)
    assert pattern.allowed_weekdays == frozenset(range(6))
    assert pattern.weekly_work_days == (5, 6)
    assert pattern.fortnightly_work_days == (11, 11)
    assert pattern.saturday_requires_weekday_cl


def test_saturday_part_time_writeback_uses_earliest_unoccupied_weekday():
    store = FakeSupabase()
    store.data["shift_definitions"] = [{
        "id": "cl-definition",
        "facility_id": "f1",
        "shift_type": "CL",
        "start_time": None,
        "end_time": None,
        "cross_midnight": False,
        "paid_minutes": 0,
        "is_working": False,
    }]
    staff = StaffInput(
        id="pt1",
        rank="CW",
        employment_type="local_pt",
        work_pattern=WorkPatternInput(saturday_requires_weekday_cl=True),
    )
    saturday = DemandSlot(
        id="sat",
        date=date(2026, 7, 4),
        day_index=0,
        shift_type="A",
        start_min=540,
        end_min=1068,
        cross_midnight=False,
        duration_min=528,
        unit_id="u1",
    )
    monday = DemandSlot(
        id="mon",
        date=date(2026, 7, 6),
        day_index=2,
        shift_type="A",
        start_min=540,
        end_min=1068,
        cross_midnight=False,
        duration_min=528,
        unit_id="u1",
    )
    inputs = SolverInputs(
        facility_id="f1",
        period_id="p1",
        period_start=date(2026, 7, 4),
        period_end=date(2026, 7, 10),
        staff=(staff,),
        demand=(saturday, monday),
    )
    assignments = [
        SimpleNamespace(staff_id="pt1", slot_id="sat"),
        SimpleNamespace(staff_id="pt1", slot_id="mon"),
    ]

    optimize._writeback_part_time_cl(
        store,
        "f1",
        "version-1",
        inputs,
        assignments,
    )

    assert store.data["shifts"][0]["shift_type"] == "CL"
    assert store.data["shifts"][0]["date"] == "2026-07-07"
    assert store.data["shifts"][0]["is_working"] is False
    assert store.data["shift_assignments"][0]["staff_id"] == "pt1"
    [debt] = store.data["future_debt_ledger"]
    assert debt["debt_type"] == "CL"
    assert debt["status"] == "settled"
    assert debt["details_json"]["recovery_date"] == "2026-07-07"


def test_saturday_part_time_writeback_defers_boundary_cl_without_definition():
    store = FakeSupabase()
    staff = StaffInput(
        id="pt1",
        rank="CW",
        employment_type="local_pt",
        work_pattern=WorkPatternInput(saturday_requires_weekday_cl=True),
    )
    saturday = DemandSlot(
        id="sat",
        date=date(2026, 7, 4),
        day_index=0,
        shift_type="A",
        start_min=540,
        end_min=1068,
        cross_midnight=False,
        duration_min=528,
        unit_id="u1",
    )
    inputs = SolverInputs(
        facility_id="f1",
        period_id="p1",
        period_start=saturday.date,
        period_end=saturday.date,
        staff=(staff,),
        demand=(saturday,),
    )

    optimize._writeback_part_time_cl(
        store,
        "f1",
        "version-1",
        inputs,
        [SimpleNamespace(staff_id="pt1", slot_id="sat")],
    )

    assert store.data.get("shifts", []) == []
    [debt] = store.data["future_debt_ledger"]
    assert debt["status"] == "open"
    assert debt["details_json"]["source_saturday"] == "2026-07-04"


def test_publish_fallback_archives_prior_operative_before_target():
    store = FakeSupabase()
    store.data["roster_versions"] = [
        {
            "id": "old",
            "facility_id": "f1",
            "period_id": "p1",
            "status": "published",
        },
        {
            "id": "target",
            "facility_id": "f1",
            "period_id": "p1",
            "status": "draft",
        },
        {
            "id": "other-period",
            "facility_id": "f1",
            "period_id": "p2",
            "status": "published",
        },
    ]

    published = roster.publish_version(
        store,
        facility_id="f1",
        roster_version_id="target",
        created_by="profile-1",
    )

    assert published["status"] == "published"
    assert next(
        row for row in store.data["roster_versions"] if row["id"] == "old"
    )["status"] == "archived"
    assert next(
        row
        for row in store.data["roster_versions"]
        if row["id"] == "other-period"
    )["status"] == "published"
    assert len(store.data["roster_publish_events"]) == 1
    assert store.data["roster_publish_events"][0]["roster_version_id"] == "target"
    assert store.data["roster_publish_events"][0]["created_by"] == "profile-1"


def test_publish_uses_atomic_database_function_when_available():
    calls = []

    class Result:
        data = [{"id": "target", "status": "published"}]

    class RpcClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return self

        def execute(self):
            return Result()

    result = roster.publish_version(
        RpcClient(),
        facility_id="f1",
        roster_version_id="target",
        created_by="ignored-by-secure-rpc",
    )

    assert result["status"] == "published"
    assert calls == [(
        "publish_roster_version",
        {
            "p_facility_id": "f1",
            "p_roster_version_id": "target",
            "p_created_by": "ignored-by-secure-rpc",
        },
    )]


def test_phase5_migration_contains_atomic_publish_and_scoped_ledgers():
    migration = (
        Path(__file__).parents[1]
        / "supabase"
        / "migrations"
        / "20260729000010_phase5_compliance_engine.sql"
    ).read_text(encoding="utf-8").lower()

    assert "uq_roster_versions_one_published_period" in migration
    assert "function public.publish_roster_version" in migration
    assert "to service_role;" in migration
    assert "to authenticated, service_role" not in migration
    assert "function public.protect_published_roster_content" in migration
    assert "function public.touch_roster_version_content" in migration
    assert "completed_at >= target.content_updated_at" in migration
    assert "source_content_updated_at = target.content_updated_at" in migration
    assert "score.constraint_score < 60" in migration
    assert "create policy roster_versions_insert" in migration
    assert "create policy roster_versions_update" in migration
    assert "create policy roster_option_scores_read" in migration
    assert "create policy roster_option_scores_update" not in migration
    assert "create policy roster_publish_events_read" in migration
    assert "drop policy if exists roster_publish_events_tenant" in migration
    assert "function public.protect_roster_option_score" in migration
    assert "function public.validate_agency_assignment_links" in migration
    assert "create policy agency_assignments_insert" in migration
