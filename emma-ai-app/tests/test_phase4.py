"""Phase 4 task scheduling: offline contract and deterministic rule tests."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from emma_core.services.scheduling import (
    EVENT_DEFAULT_REQUIREMENTS,
    evaluate_event_staffing,
    evaluate_floor_coverage,
    event_requirements_for,
    event_type_catalogue,
    normalise_event_type,
    task_assignment_issues,
    task_eligibility_issues,
)


client = TestClient(app, raise_server_exceptions=False)


def test_openapi_documents_phase4_surface():
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/task-assignments",
        "/task-assignments/{task_assignment_id}",
        "/facility-events",
        "/facility-events/{event_id}",
        "/validate-roster",
    ):
        assert path in paths


def test_phase4_tables_keep_the_facility_rls_boundary():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20260729000009_phase4_task_scheduling.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "staff_qualifications",
        "event_staffing_requirements",
        "floor_min_staffing_rules",
    ):
        assert f"alter table {table} enable row level security" in migration
        assert f"{table}_tenant" in migration
    assert len(re.findall(r"facility_id\s+uuid not null", migration)) >= 3


def test_unaudited_external_worker_is_limited_to_a3_or_p3():
    staff = {"rank": "HW", "employment_type": "agency"}
    blocked = task_eligibility_issues(
        {"task_code": "A1", "required_rank": "HW"}, staff)
    allowed = task_eligibility_issues(
        {"task_code": "A3", "required_rank": "HW"}, staff)

    assert any(issue["reason"] == "unaudited_external" for issue in blocked)
    assert allowed == []


def test_daily_task_codes_are_profession_specific():
    issues = task_eligibility_issues(
        {"task_code": "A1", "required_rank": "HW"},
        {"rank": "RN", "employment_type": "local_ft"},
    )
    assert issues == [{"reason": "rank", "required": "HW", "actual": "RN"}]
    assert task_eligibility_issues(
        {"task_code": "A3", "required_rank": "CW"},
        {"rank": "HCA", "employment_type": "local_ft"},
    ) == []


def test_qualification_and_new_staff_restrictions_are_data_driven():
    task = {
        "task_code": "A1",
        "required_rank": "HW",
        "requires_audit": True,
        "required_qualification_json": {"all_of": ["medication_audited"]},
        "is_restricted": True,
    }
    staff = {"rank": "HW", "employment_type": "local_ft"}

    reasons = {row["reason"] for row in task_eligibility_issues(
        task, staff, {"new_staff"})}
    assert {"medication_audit", "qualification_all_of", "new_staff_restricted"} <= reasons
    assert task_eligibility_issues(
        task, staff, {"new_staff", "medication_audited", "mentor"}) == []


def test_task_code_must_match_the_rostered_shift():
    issues = task_assignment_issues(
        {"task_code": "P3", "required_rank": "HW", "shift_type": "P"},
        {"rank": "HW", "employment_type": "local_ft"},
        set(),
        {"shift_type": "A", "unit_id": None},
    )
    assert issues == [{"reason": "shift_type", "required": "P", "actual": "A"}]


def test_event_templates_capture_additive_and_concurrent_work():
    haircut = event_requirements_for("hair cut")
    podiatry = event_requirements_for("podiatry")
    records = event_requirements_for("medication_record")

    assert haircut == [{
        "rank": "CW|HCA", "count": 1, "is_additive": True,
        "notes": "One additional care worker for the event.",
    }]
    assert {row["rank"] for row in records} == {"EN", "HW"}
    assert all(not row["is_additive"] for row in podiatry)


def _shift(shift_id: str, unit_id: str, shift_type: str, start: str, end: str):
    return {
        "id": shift_id, "date": "2026-07-06", "unit_id": unit_id,
        "shift_type": shift_type, "start_time": start, "end_time": end,
        "cross_midnight": end <= start, "is_working": True,
    }


def _assignment(assignment_id: str, shift_id: str, staff_id: str, role: str):
    return {
        "id": assignment_id, "shift_id": shift_id, "staff_id": staff_id,
        "role": role, "status": "assigned",
    }


def test_floor_rule_detects_minute_level_shortfall():
    shifts = [
        _shift("s1", "u6", "7A", "07:00", "19:00"),
        _shift("s2", "u6", "7A", "07:00", "19:00"),
    ]
    assignments = [
        _assignment("a1", "s1", "p1", "HCA"),
        _assignment("a2", "s2", "p2", "HCA"),
    ]
    staff = {
        "p1": {"employment_type": "imported_labor"},
        "p2": {"employment_type": "local_ft"},
    }
    rules = [{
        "id": "r1", "unit_id": "u6", "time_window_start": "07:00",
        "time_window_end": "17:00", "rank": "HCA", "min_count": 3,
        "condition_json": {"weekdays": [0, 1, 2, 3, 4],
                           "required_shift_types": ["7A"]},
        "active": True,
    }]

    violations = evaluate_floor_coverage(
        rules=rules, units=[{"id": "u6", "name": "6/F", "code": "6F"}],
        shifts=shifts, assignments=assignments, staff_by_id=staff)

    assert len(violations) == 1
    assert violations[0]["details"]["actual"] == 2
    assert violations[0]["details"]["required"] == 3


def test_2f_composition_requires_local_p_shift_support():
    shifts = [
        _shift("s1", "u2", "7A", "07:00", "19:00"),
        _shift("s2", "u2", "7A", "07:00", "19:00"),
        _shift("s3", "u2", "7A", "07:00", "16:00"),
    ]
    assignments = [
        _assignment("a1", "s1", "imp1", "HCA"),
        _assignment("a2", "s2", "imp2", "HCA"),
        _assignment("a3", "s3", "local1", "HCA"),
    ]
    staff = {
        "imp1": {"employment_type": "imported_labor"},
        "imp2": {"employment_type": "imported_labor"},
        "local1": {"employment_type": "local_ft"},
        "local2": {"employment_type": "local_ft"},
    }
    rule = {
        "id": "r2", "unit_id": "u2", "time_window_start": "16:00",
        "time_window_end": "21:30", "rank": "HCA", "min_count": 1,
        "condition_json": {
            "when_7a_composition": {"imported_labor": 2, "local_ft": 1},
            "required_shift_types": ["P"], "employment_types": ["local_ft"],
        },
        "active": True,
    }
    kwargs = {
        "rules": [rule], "units": [{"id": "u2", "name": "2/F", "code": "2F"}],
        "staff_by_id": staff,
    }
    assert len(evaluate_floor_coverage(
        shifts=shifts, assignments=assignments, **kwargs)) == 1

    shifts.append(_shift("s4", "u2", "P", "12:30", "21:30"))
    assignments.append(_assignment("a4", "s4", "local2", "HCA"))
    assert evaluate_floor_coverage(
        shifts=shifts, assignments=assignments, **kwargs) == []


def test_event_staffing_violation_carries_event_evidence():
    event = {
        "id": "e1", "event_type": "CGAT", "title": "CGAT",
        "date": "2026-07-06", "start_at": "2026-07-06T09:00:00+00:00",
        "end_at": "2026-07-06T12:00:00+00:00", "unit_id": None,
    }
    shift = _shift("s1", "u1", "A", "07:00", "15:00")
    violations = evaluate_event_staffing(
        events=[event],
        requirements=[{"id": "er1", "event_id": "e1", "rank": "RN",
                       "count": 1, "is_additive": True}],
        shifts=[shift],
        assignments=[_assignment("a1", "s1", "p1", "HW")],
        staff_by_id={"p1": {"employment_type": "local_ft"}},
    )
    assert violations[0]["event_id"] == "e1"
    assert violations[0]["rule_code"] == "event_staffing"


# ── 4.2 · the event-type catalogue (Cherry, 1 Aug 2026) ─────────────────────
def test_event_type_catalogue_is_the_only_list_the_ui_needs():
    """One endpoint, one list. The picker must not be able to offer a type the
    server would reject, nor miss one it accepts."""
    catalogue = event_type_catalogue()
    codes = [row["code"] for row in catalogue]

    assert codes, "the catalogue must not be empty"
    assert len(codes) == len(set(codes)), "duplicate codes in the catalogue"
    for row in catalogue:
        assert row["label_zh"] and row["label_en"], f"{row['code']} has no label"
        # Every code the catalogue publishes must survive its own normaliser -
        # otherwise the modal sends back something validation rewrites.
        assert normalise_event_type(row["code"]) == row["code"]
        assert row["templated"] == bool(row["default_requirements"])


def test_every_templated_event_type_is_published():
    """A type with a staffing template that the picker cannot offer is a rule
    nobody can trigger."""
    published = {row["code"] for row in event_type_catalogue()}
    templated = {code for code, reqs in EVENT_DEFAULT_REQUIREMENTS.items() if reqs}
    assert templated <= published, f"missing from the catalogue: {templated - published}"


def test_catalogue_publishes_the_aliases_the_importer_writes():
    """The workbook importer maps 剪髮 to `haircut`, so events already in the
    database carry alias spellings. A UI that has to render one needs to know it
    is the same type."""
    by_code = {row["code"]: row for row in event_type_catalogue()}
    assert "haircut" in by_code["hair_cutting"]["aliases"]
    for row in by_code.values():
        for alias in row["aliases"]:
            assert normalise_event_type(alias) == row["code"]


def test_event_types_endpoint_is_declared_before_the_id_route():
    """`/facility-events/types` must not be matched as an event id."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/facility-events/types" in paths
