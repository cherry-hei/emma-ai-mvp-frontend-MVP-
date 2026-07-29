"""Phase 4 task-based scheduling.

This module owns the three deterministic Phase 4 domains:

* task-code eligibility and task-assignment CRUD;
* special-event staffing overlays;
* floor/unit operational coverage.

The pure evaluators are intentionally separated from PostgREST orchestration so
Phase 5 can reuse the exact same rules in automatic compliance checks and Phase
6 can explain failures without inventing a second rule implementation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as Date, datetime as DateTime
from typing import Iterable
from uuid import UUID

from ..constants import can_cover_rank
from ..shifttime import day_spans, duty_spans, to_minutes

PHASE4_RULE_CODES = ("task_eligibility", "event_staffing", "floor_coverage")
TASK_SOURCE_TYPES = {"manual", "event", "solver", "legacy_cell"}
UNAUDITED_EXTERNAL_TASKS = {"A3", "P3"}
EXTERNAL_TASK_TYPES = {"agency", "outsource", "casual"}


EVENT_TYPE_ALIASES = {
    "haircut": "hair_cutting",
    "hair_cut": "hair_cutting",
    "training": "meeting_training",
    "meeting": "meeting_training",
    "medication_board": "medication_board_checking",
    "medication_record": "medication_record_checking",
    "weighing": "monthly_weighing",
}

EVENT_DEFAULT_REQUIREMENTS: dict[str, tuple[dict, ...]] = {
    "hair_cutting": (
        {"rank": "CW|HCA", "count": 1, "is_additive": True,
         "notes": "One additional care worker for the event."},
    ),
    "cgat": (
        {"rank": "RN", "count": 1, "is_additive": True},
        {"rank": "HW", "count": 1, "is_additive": True},
    ),
    "medication_board_checking": (
        {"rank": "HW|EN", "count": 1, "is_additive": True},
    ),
    "medication_record_checking": (
        {"rank": "EN", "count": 1, "is_additive": True},
        {"rank": "HW", "count": 1, "is_additive": True},
    ),
    # These are concurrent duties for already-rostered staff, not extra heads.
    "podiatry": (
        {"rank": "HW", "count": 1, "is_additive": False},
        {"rank": "CW|HCA", "count": 1, "is_additive": False},
    ),
    "monthly_weighing": (
        {"rank": "CW|HCA", "count": 1, "is_additive": False},
    ),
    # Visiting, meetings/training and PGT are manager-assessed. They are accepted
    # with an explicit requirement list rather than a guessed fixed headcount.
    "visiting": (),
    "meeting_training": (),
    "pgt": (),
}


def _normalise_code(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _persisted_task_assignment_id(value: object) -> str | None:
    """Return only identifiers that can satisfy the audit table's UUID FK.

    Read-only validation synthesises ``legacy:...`` references for task labels
    that still live in the old shift-assignment cell. Those references are
    useful evidence, but they are not rows in ``task_assignments`` and must not
    be written into its UUID foreign-key column.
    """
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def task_rank_matches(actual_rank: str | None, required_rank: str | None) -> bool:
    """Task codes are profession-specific; CW and HCA are the care-worker alias."""
    if not required_rank:
        return True
    if actual_rank == required_rank:
        return True
    return {actual_rank, required_rank} == {"CW", "HCA"}


def normalise_event_type(value: str) -> str:
    code = _normalise_code(value)
    return EVENT_TYPE_ALIASES.get(code, code)


def event_requirements_for(
    event_type: str,
    explicit: Iterable[dict] | None = None,
) -> list[dict]:
    """Return a defensive copy of explicit or facility-default requirements.

    ``None`` means "use the event template"; an explicit empty list means the
    manager intentionally assessed no staffing requirement.
    """
    source = EVENT_DEFAULT_REQUIREMENTS.get(normalise_event_type(event_type), ())
    if explicit is not None:
        source = tuple(dict(row) for row in explicit)
    return [{
        "rank": str(row["rank"]).upper(),
        "count": int(row.get("count") or 1),
        "is_additive": bool(row.get("is_additive", True)),
        "notes": row.get("notes"),
    } for row in source]


def _required_qualifications(config) -> tuple[set[str], set[str], set[str]]:
    """Normalise the versionable JSON rule into all/any/none capability sets."""
    if not config:
        return set(), set(), set()
    if isinstance(config, str):
        config = {"all_of": [config]}
    elif isinstance(config, list):
        config = {"all_of": config}
    if not isinstance(config, dict):
        return set(), set(), set()

    def values(key: str) -> set[str]:
        raw = config.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        return {_normalise_code(str(value)) for value in raw if value}

    return values("all_of"), values("any_of"), values("none_of")


def task_eligibility_issues(
    task: dict,
    staff: dict,
    qualification_types: Iterable[str] = (),
) -> list[dict]:
    """Pure task eligibility check used by both writes and roster validation."""
    capabilities = {_normalise_code(q) for q in qualification_types}
    if staff.get("is_audited_for_medication"):
        capabilities.add("medication_audited")
    if staff.get("is_mentor"):
        capabilities.add("mentor")

    issues: list[dict] = []
    required_rank = task.get("required_rank")
    if not task_rank_matches(staff.get("rank"), required_rank):
        issues.append({
            "reason": "rank",
            "required": required_rank,
            "actual": staff.get("rank"),
        })

    task_unit_id = task.get("unit_id")
    if task_unit_id and task_unit_id != staff.get("primary_unit_id"):
        issues.append({
            "reason": "unit",
            "required": task_unit_id,
            "actual": staff.get("primary_unit_id"),
        })

    code = str(task.get("task_code") or "").upper()
    employment_type = str(staff.get("employment_type") or "")
    audited = "medication_audited" in capabilities
    if (employment_type in EXTERNAL_TASK_TYPES and not audited
            and code not in UNAUDITED_EXTERNAL_TASKS):
        issues.append({
            "reason": "unaudited_external",
            "allowed_task_codes": sorted(UNAUDITED_EXTERNAL_TASKS),
            "actual_task_code": code,
        })

    if task.get("requires_audit") and not audited:
        issues.append({"reason": "medication_audit", "required": "medication_audited"})

    all_of, any_of, none_of = _required_qualifications(
        task.get("required_qualification_json"))
    missing = sorted(all_of - capabilities)
    if missing:
        issues.append({"reason": "qualification_all_of", "missing": missing})
    if any_of and not (any_of & capabilities):
        issues.append({"reason": "qualification_any_of", "required": sorted(any_of)})
    blocked = sorted(none_of & capabilities)
    if blocked:
        issues.append({"reason": "qualification_none_of", "blocked": blocked})

    # A facility marks new staff with a qualification flag so restrictions remain
    # data-driven. Mentors are allowed to perform restricted duties.
    if task.get("is_restricted") and "new_staff" in capabilities and "mentor" not in capabilities:
        issues.append({"reason": "new_staff_restricted", "required": "mentor"})
    return issues


def _rank_matches(actual: str | None, expression: str | None) -> bool:
    if not expression:
        return True
    return any(can_cover_rank(actual, rank.strip())
               for rank in expression.upper().split("|") if rank.strip())


def _window_spans(start: str, end: str) -> list[tuple[int, int]]:
    start_min, end_min = to_minutes(start), to_minutes(end)
    if start_min is None or end_min is None:
        return [(0, 1440)]
    return day_spans(start_min, end_min, end_min <= start_min)


def _minimum_concurrent_count(
    *,
    shifts: list[dict],
    assignments: list[dict],
    staff_by_id: dict[str, dict],
    window_start: str,
    window_end: str,
    unit_id: str | None,
    rank: str | None,
    required_shift_types: Iterable[str] = (),
    employment_types: Iterable[str] = (),
) -> int:
    shift_by_id = {row["id"]: row for row in shifts}
    allowed_shifts = {str(value).upper() for value in required_shift_types}
    allowed_employment = {str(value) for value in employment_types}
    intervals_by_staff: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for assignment in assignments:
        if assignment.get("status") == "cancelled":
            continue
        shift = shift_by_id.get(assignment.get("shift_id"))
        if not shift or not shift.get("is_working", True):
            continue
        if unit_id and shift.get("unit_id") != unit_id:
            continue
        if allowed_shifts and str(shift.get("shift_type") or "").upper() not in allowed_shifts:
            continue
        if not _rank_matches(assignment.get("role"), rank):
            continue
        staff_id = assignment.get("staff_id")
        staff = staff_by_id.get(staff_id, {}) if staff_id else {}
        if allowed_employment and staff.get("employment_type") not in allowed_employment:
            continue
        identity = staff_id or f"agency:{assignment.get('id')}"
        intervals_by_staff[identity].extend(duty_spans(shift))

    minimum: int | None = None
    for window in _window_spans(window_start, window_end):
        clipped_by_staff: dict[str, list[tuple[int, int]]] = {}
        points = {window[0], window[1]}
        for staff_id, intervals in intervals_by_staff.items():
            clipped: list[tuple[int, int]] = []
            for start, end in intervals:
                low, high = max(start, window[0]), min(end, window[1])
                if low < high:
                    clipped.append((low, high))
                    points.update((low, high))
            if clipped:
                clipped_by_staff[staff_id] = clipped

        ordered = sorted(points)
        for low, high in zip(ordered, ordered[1:]):
            if low == high:
                continue
            actual = sum(
                1 for intervals in clipped_by_staff.values()
                if any(start <= low and end >= high for start, end in intervals)
            )
            minimum = actual if minimum is None else min(minimum, actual)
    return minimum or 0


def _date_value(value) -> Date:
    if isinstance(value, DateTime):
        return value.date()
    if isinstance(value, Date):
        return value
    return Date.fromisoformat(str(value)[:10])


def _time_value(value, fallback: str) -> str:
    if not value:
        return fallback
    if isinstance(value, DateTime):
        return value.strftime("%H:%M")
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    return text[:5]


def _rule_unit_id(rule: dict, units: list[dict]) -> str | None:
    if rule.get("unit_id"):
        return rule["unit_id"]
    floor = str(rule.get("floor") or "").casefold()
    for unit in units:
        if floor in {str(unit.get("code") or "").casefold(),
                     str(unit.get("name") or "").casefold()}:
            return unit["id"]
    return None


def _composition_matches(
    condition: dict,
    *,
    unit_id: str | None,
    shifts: list[dict],
    assignments: list[dict],
    staff_by_id: dict[str, dict],
) -> bool:
    required = condition.get("when_7a_composition")
    if not required:
        return True
    shift_by_id = {shift["id"]: shift for shift in shifts}
    actual: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        shift = shift_by_id.get(assignment.get("shift_id"))
        if (not shift or shift.get("unit_id") != unit_id
                or str(shift.get("shift_type") or "").upper() != "7A"
                or assignment.get("status") == "cancelled"):
            continue
        staff = staff_by_id.get(assignment.get("staff_id"), {})
        employment = staff.get("employment_type")
        if employment:
            actual[employment].add(assignment["staff_id"])
    return all(len(actual.get(kind, set())) >= int(count)
               for kind, count in required.items())


def evaluate_floor_coverage(
    *,
    rules: list[dict],
    units: list[dict],
    shifts: list[dict],
    assignments: list[dict],
    staff_by_id: dict[str, dict],
) -> list[dict]:
    """Evaluate configurable floor rules at minute-level concurrency."""
    shifts_by_date: dict[str, list[dict]] = defaultdict(list)
    for shift in shifts:
        shifts_by_date[str(shift["date"])[:10]].append(shift)

    assignments_by_date: dict[str, list[dict]] = defaultdict(list)
    shift_date = {shift["id"]: str(shift["date"])[:10] for shift in shifts}
    for assignment in assignments:
        if assignment.get("shift_id") in shift_date:
            assignments_by_date[shift_date[assignment["shift_id"]]].append(assignment)

    violations: list[dict] = []
    for date_text, day_shifts in sorted(shifts_by_date.items()):
        day = Date.fromisoformat(date_text)
        day_assignments = assignments_by_date[date_text]
        for rule in rules:
            if not rule.get("active", True):
                continue
            if rule.get("effective_from") and day < _date_value(rule["effective_from"]):
                continue
            if rule.get("effective_to") and day > _date_value(rule["effective_to"]):
                continue
            condition = rule.get("condition_json") or {}
            weekdays = condition.get("weekdays")
            if weekdays is not None and day.weekday() not in {int(v) for v in weekdays}:
                continue
            unit_id = _rule_unit_id(rule, units)
            if not unit_id:
                continue
            if not _composition_matches(
                condition, unit_id=unit_id, shifts=day_shifts,
                assignments=day_assignments, staff_by_id=staff_by_id,
            ):
                continue

            actual = _minimum_concurrent_count(
                shifts=day_shifts,
                assignments=day_assignments,
                staff_by_id=staff_by_id,
                window_start=str(rule["time_window_start"])[:5],
                window_end=str(rule["time_window_end"])[:5],
                unit_id=unit_id,
                rank=rule.get("rank"),
                required_shift_types=condition.get("required_shift_types") or (),
                employment_types=condition.get("employment_types") or (),
            )
            required = int(rule.get("min_count") or 0)
            if actual >= required:
                continue
            label = next((unit.get("name") for unit in units if unit["id"] == unit_id), unit_id)
            violations.append({
                "rule_code": "floor_coverage",
                "date": date_text,
                "unit_id": unit_id,
                "severity": "hard",
                "message": (
                    f"{label} {str(rule['time_window_start'])[:5]}-"
                    f"{str(rule['time_window_end'])[:5]} requires {required} "
                    f"{rule.get('rank')}; minimum on duty is {actual}."
                ),
                "details": {
                    "rule_id": rule.get("id"),
                    "required": required,
                    "actual": actual,
                    "condition": condition,
                },
                "resolved": False,
            })
    return violations


def evaluate_event_staffing(
    *,
    events: list[dict],
    requirements: list[dict],
    shifts: list[dict],
    assignments: list[dict],
    staff_by_id: dict[str, dict],
) -> list[dict]:
    """Check that event-required ranks are present during the event window."""
    requirements_by_event: dict[str, list[dict]] = defaultdict(list)
    for row in requirements:
        requirements_by_event[row["event_id"]].append(row)
    shifts_by_date: dict[str, list[dict]] = defaultdict(list)
    for shift in shifts:
        shifts_by_date[str(shift["date"])[:10]].append(shift)
    shift_date = {shift["id"]: str(shift["date"])[:10] for shift in shifts}
    assignments_by_date: dict[str, list[dict]] = defaultdict(list)
    for assignment in assignments:
        date_text = shift_date.get(assignment.get("shift_id"))
        if date_text:
            assignments_by_date[date_text].append(assignment)

    violations: list[dict] = []
    for event in events:
        date_text = str(event.get("date") or event.get("event_date"))[:10]
        event_requirements = requirements_by_event.get(event["id"], [])
        for requirement in event_requirements:
            actual = _minimum_concurrent_count(
                shifts=shifts_by_date.get(date_text, []),
                assignments=assignments_by_date.get(date_text, []),
                staff_by_id=staff_by_id,
                window_start=_time_value(event.get("start_at"), "00:00"),
                window_end=_time_value(event.get("end_at"), "24:00"),
                unit_id=event.get("unit_id"),
                rank=requirement.get("rank"),
            )
            required = int(requirement.get("count") or 1)
            if actual >= required:
                continue
            violations.append({
                "rule_code": "event_staffing",
                "date": date_text,
                "unit_id": event.get("unit_id"),
                "event_id": event["id"],
                "severity": "hard",
                "message": (
                    f"{event.get('title') or event.get('event_type')} requires "
                    f"{required} {requirement.get('rank')}; minimum on duty is {actual}."
                ),
                "details": {
                    "requirement_id": requirement.get("id"),
                    "required": required,
                    "actual": actual,
                    "is_additive": bool(requirement.get("is_additive", True)),
                },
                "resolved": False,
            })
    return violations


def _active_qualification_map(
    client,
    facility_id: str,
    staff_ids: Iterable[str],
    *,
    on_date: Date | str | None = None,
) -> dict[str, set[str]]:
    ids = list(staff_ids)
    if not ids:
        return {}
    rows = (client.table("staff_qualifications").select("*")
            .eq("facility_id", facility_id).in_("staff_id", ids)
            .eq("is_active", True).execute().data)
    return _qualification_map_for_date(rows, on_date or Date.today())


def _qualification_map_for_date(
    rows: Iterable[dict],
    on_date: Date | str,
) -> dict[str, set[str]]:
    day = _date_value(on_date)
    out: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not row.get("is_active", True):
            continue
        if row.get("effective_from") and day < _date_value(row["effective_from"]):
            continue
        if row.get("expiry_date") and day > _date_value(row["expiry_date"]):
            continue
        out[row["staff_id"]].add(row["qualification_type"])
    return out


def _task_definition(client, facility_id: str, task_id: str) -> dict:
    rows = (client.table("task_definitions").select("*")
            .eq("id", task_id).eq("active", True).execute().data)
    if not rows or rows[0].get("facility_id") not in (None, facility_id):
        raise ValueError("task definition not found")
    return rows[0]


def _assignment_context(client, facility_id: str, assignment_id: str):
    assignments = (client.table("shift_assignments").select("*")
                   .eq("facility_id", facility_id).eq("id", assignment_id)
                   .execute().data)
    if not assignments:
        raise ValueError("shift assignment not found")
    assignment = assignments[0]
    shifts = (client.table("shifts").select("*")
              .eq("facility_id", facility_id).eq("id", assignment["shift_id"])
              .execute().data)
    if not shifts:
        raise ValueError("shift not found")
    staff_rows = (client.table("staff").select("*")
                  .eq("facility_id", facility_id).eq("id", assignment["staff_id"])
                  .execute().data)
    if not staff_rows:
        raise ValueError("assigned staff member not found")
    return assignment, shifts[0], staff_rows[0]


def _persist_violations(
    client,
    facility_id: str,
    roster_version_id: str | None,
    violations: Iterable[dict],
) -> None:
    rows = []
    for violation in violations:
        rows.append({
            "facility_id": facility_id,
            "roster_version_id": roster_version_id,
            "rule_code": violation["rule_code"],
            "shift_id": violation.get("shift_id"),
            "date": violation.get("date"),
            "unit_id": violation.get("unit_id"),
            "task_assignment_id": violation.get("task_assignment_id"),
            "event_id": violation.get("event_id"),
            "severity": violation.get("severity", "hard"),
            "message": violation.get("message"),
            "details_json": violation.get("details") or {},
            "resolved": False,
        })
    if rows:
        client.table("violation_log").insert(rows).execute()


def _raise_task_issues(
    client,
    facility_id: str,
    assignment: dict,
    shift: dict,
    task: dict,
    issues: list[dict],
) -> None:
    if not issues:
        return
    label = task.get("task_name") or task.get("task_code")
    violation = {
        "rule_code": "task_eligibility",
        "shift_id": shift["id"],
        "date": str(shift["date"])[:10],
        "unit_id": shift.get("unit_id"),
        "severity": "hard",
        "message": f"{label} is not eligible for the assigned staff member.",
        "details": {
            "shift_assignment_id": assignment["id"],
            "task_id": task["id"],
            "issues": issues,
        },
    }
    _persist_violations(
        client, facility_id, shift.get("roster_version_id"), [violation])
    reasons = ", ".join(issue["reason"] for issue in issues)
    raise ValueError(f"task assignment is not eligible: {reasons}")


def task_assignment_issues(
    task: dict,
    staff: dict,
    qualifications: Iterable[str],
    shift: dict,
) -> list[dict]:
    issues = task_eligibility_issues(task, staff, qualifications)
    required_shift = task.get("shift_type")
    actual_shift = shift.get("shift_type")
    if required_shift and required_shift != actual_shift:
        issues.append({
            "reason": "shift_type",
            "required": required_shift,
            "actual": actual_shift,
        })
    task_unit = task.get("unit_id")
    if task_unit and shift.get("unit_id") != task_unit:
        issues.append({
            "reason": "shift_unit",
            "required": task_unit,
            "actual": shift.get("unit_id"),
        })
    return issues


def validate_task_labels(
    client,
    facility_id: str,
    *,
    roster_version_id: str,
    staff_id: str,
    shift_type: str,
    on_date: Date | str,
    labels: Iterable[str],
) -> None:
    """Validate the legacy roster-cell task array before mutating the cell."""
    labels = list(dict.fromkeys(label for label in labels if label))
    if not labels:
        return
    staff_rows = (client.table("staff").select("*")
                  .eq("facility_id", facility_id).eq("id", staff_id).execute().data)
    if not staff_rows:
        raise ValueError("staff member not found")
    staff = staff_rows[0]
    definitions = (client.table("task_definitions").select("*")
                   .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
                   .eq("active", True).execute().data)
    qualifications = _active_qualification_map(
        client, facility_id, [staff_id], on_date=on_date).get(staff_id, set())

    violations: list[dict] = []
    for label in labels:
        candidates = [
            task for task in definitions
            if label in {task.get("task_name"), task.get("task_code")}
        ]
        if not candidates:
            violations.append({
                "rule_code": "task_eligibility",
                "severity": "hard",
                "message": f"Unknown task '{label}'.",
                "details": {"reason": "unknown_task", "task_label": label},
            })
            continue
        compatible = [
            task for task in candidates
            if (not task.get("shift_type") or task["shift_type"] == shift_type)
            and task_rank_matches(staff.get("rank"), task.get("required_rank"))
        ]
        task = (compatible or candidates)[0]
        issues = task_assignment_issues(
            task, staff, qualifications,
            {"shift_type": shift_type, "unit_id": staff.get("primary_unit_id")},
        )
        if issues:
            violations.append({
                "rule_code": "task_eligibility",
                "severity": "hard",
                "message": f"{label} is not eligible for this staff/shift.",
                "details": {"task_id": task["id"], "issues": issues},
            })
    if violations:
        _persist_violations(client, facility_id, roster_version_id, violations)
        raise ValueError(violations[0]["message"])


def list_task_assignments(
    client,
    facility_id: str,
    *,
    roster_version_id: str | None = None,
    shift_assignment_id: str | None = None,
) -> list[dict]:
    query = client.table("task_assignments").select("*").eq("facility_id", facility_id)
    if roster_version_id:
        query = query.eq("roster_version_id", roster_version_id)
    if shift_assignment_id:
        query = query.eq("shift_assignment_id", shift_assignment_id)
    return query.order("start_at").execute().data


def _update_legacy_task_labels(
    client,
    assignment: dict,
    *,
    remove: str | None = None,
    add: str | None = None,
) -> None:
    labels = list(assignment.get("tasks") or [])
    if remove:
        labels = [label for label in labels if label != remove]
    if add and add not in labels:
        labels.append(add)
    (client.table("shift_assignments").update({"tasks": labels})
     .eq("id", assignment["id"]).execute())


def create_task_assignment(client, facility_id: str, payload: dict) -> dict:
    source_type = payload.get("source_type") or "manual"
    if source_type not in TASK_SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {sorted(TASK_SOURCE_TYPES)}")
    assignment, shift, staff = _assignment_context(
        client, facility_id, payload["shift_assignment_id"])
    task = _task_definition(client, facility_id, payload["task_id"])
    qualifications = _active_qualification_map(
        client, facility_id, [staff["id"]], on_date=shift["date"]).get(
            staff["id"], set())
    _raise_task_issues(
        client, facility_id, assignment, shift, task,
        task_assignment_issues(task, staff, qualifications, shift),
    )
    label = task.get("task_name") or task["task_code"]
    row = {
        "facility_id": facility_id,
        "roster_version_id": shift.get("roster_version_id"),
        "shift_assignment_id": assignment["id"],
        "staff_id": staff["id"],
        "task_id": task["id"],
        "task_label": label,
        "start_at": payload.get("start_at"),
        "end_at": payload.get("end_at"),
        "scheduled_time": (
            _time_value(payload.get("start_at"), "")
            if payload.get("start_at") else None
        ),
        "source_type": source_type,
        "priority": "high" if task.get("is_restricted") or task.get("requires_audit") else "normal",
        "task_status": "pending",
    }
    existing = (client.table("task_assignments").select("*")
                .eq("facility_id", facility_id)
                .eq("shift_assignment_id", assignment["id"])
                .eq("task_label", label).execute().data)
    if existing:
        result = (client.table("task_assignments").update(row)
                  .eq("id", existing[0]["id"]).execute().data[0])
    else:
        result = client.table("task_assignments").insert(row).execute().data[0]
    _update_legacy_task_labels(client, assignment, add=label)
    return result


def update_task_assignment(
    client,
    facility_id: str,
    task_assignment_id: str,
    patch: dict,
) -> dict:
    rows = (client.table("task_assignments").select("*")
            .eq("facility_id", facility_id).eq("id", task_assignment_id)
            .execute().data)
    if not rows:
        raise ValueError("task assignment not found")
    current = rows[0]
    assignment, shift, staff = _assignment_context(
        client, facility_id, current["shift_assignment_id"])
    task = _task_definition(
        client, facility_id, patch.get("task_id") or current["task_id"])
    source_type = patch.get("source_type", current.get("source_type") or "manual")
    if source_type not in TASK_SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {sorted(TASK_SOURCE_TYPES)}")
    qualifications = _active_qualification_map(
        client, facility_id, [staff["id"]], on_date=shift["date"]).get(
            staff["id"], set())
    _raise_task_issues(
        client, facility_id, assignment, shift, task,
        task_assignment_issues(task, staff, qualifications, shift),
    )

    new_label = task.get("task_name") or task["task_code"]
    update = {
        "task_id": task["id"],
        "task_label": new_label,
        "source_type": source_type,
    }
    for field in ("start_at", "end_at"):
        if field in patch:
            update[field] = patch[field]
    if "start_at" in patch:
        update["scheduled_time"] = (
            _time_value(patch["start_at"], "") if patch["start_at"] else None
        )
    result = (client.table("task_assignments").update(update)
              .eq("id", task_assignment_id).execute().data[0])
    _update_legacy_task_labels(
        client, assignment, remove=current.get("task_label"), add=new_label)
    return result


def delete_task_assignment(client, facility_id: str, task_assignment_id: str) -> None:
    rows = (client.table("task_assignments").select("*")
            .eq("facility_id", facility_id).eq("id", task_assignment_id)
            .execute().data)
    if not rows:
        return
    current = rows[0]
    assignment, _, _ = _assignment_context(
        client, facility_id, current["shift_assignment_id"])
    (client.table("task_assignments").delete()
     .eq("facility_id", facility_id).eq("id", task_assignment_id).execute())
    _update_legacy_task_labels(client, assignment, remove=current.get("task_label"))


def sync_task_rows_for_assignment(
    client,
    facility_id: str,
    assignment_id: str,
) -> list[dict]:
    from .tasks import sync_assignment_tasks, task_definitions_by_label

    assignment, shift, _ = _assignment_context(client, facility_id, assignment_id)
    return sync_assignment_tasks(
        client, facility_id, assignment, shift,
        task_definitions_by_label(client, facility_id),
    )


def _validate_unit(client, facility_id: str, unit_id: str | None) -> None:
    if not unit_id:
        return
    rows = (client.table("facility_units").select("id")
            .eq("facility_id", facility_id).eq("id", unit_id).execute().data)
    if not rows:
        raise ValueError("facility unit not found")


def _insert_event_requirements(
    client,
    facility_id: str,
    event_id: str,
    requirements: list[dict],
) -> list[dict]:
    if not requirements:
        return []
    rows = [{
        "facility_id": facility_id,
        "event_id": event_id,
        **requirement,
    } for requirement in requirements]
    return client.table("event_staffing_requirements").insert(rows).execute().data


def _event_output(event: dict, requirements: list[dict]) -> dict:
    return {
        "id": event["id"],
        "event_type": event["event_type"],
        "event_date": event["date"],
        "start_at": event.get("start_at"),
        "end_at": event.get("end_at"),
        "unit_id": event.get("unit_id"),
        "title": event.get("title"),
        "notes": event.get("notes"),
        "staffing_requirements": requirements,
    }


def list_facility_events(
    client,
    facility_id: str,
    *,
    date_from: Date | str | None = None,
    date_to: Date | str | None = None,
) -> list[dict]:
    query = client.table("facility_events").select("*").eq("facility_id", facility_id)
    if date_from:
        query = query.gte("date", str(date_from))
    if date_to:
        query = query.lte("date", str(date_to))
    events = query.order("date").execute().data
    if not events:
        return []
    requirements = (client.table("event_staffing_requirements").select("*")
                    .eq("facility_id", facility_id)
                    .in_("event_id", [event["id"] for event in events])
                    .execute().data)
    by_event: dict[str, list[dict]] = defaultdict(list)
    for row in requirements:
        by_event[row["event_id"]].append(row)
    return [_event_output(event, by_event.get(event["id"], [])) for event in events]


def create_facility_event(client, facility_id: str, payload: dict) -> dict:
    _validate_unit(client, facility_id, payload.get("unit_id"))
    event_type = normalise_event_type(payload["event_type"])
    requirements = event_requirements_for(
        event_type, payload.get("staffing_requirements"))
    event_row = {
        "facility_id": facility_id,
        "event_type": event_type,
        "date": str(payload["event_date"]),
        "start_at": payload.get("start_at"),
        "end_at": payload.get("end_at"),
        "unit_id": payload.get("unit_id"),
        "title": payload.get("title"),
        "notes": payload.get("notes"),
        "required_staffing_json": requirements,
    }
    event = client.table("facility_events").insert(event_row).execute().data[0]
    try:
        saved = _insert_event_requirements(
            client, facility_id, event["id"], requirements)
    except Exception:
        client.table("facility_events").delete().eq("id", event["id"]).execute()
        raise
    return _event_output(event, saved)


def update_facility_event(
    client,
    facility_id: str,
    event_id: str,
    patch: dict,
) -> dict:
    rows = (client.table("facility_events").select("*")
            .eq("facility_id", facility_id).eq("id", event_id).execute().data)
    if not rows:
        raise ValueError("facility event not found")
    current = rows[0]
    _validate_unit(client, facility_id, patch.get("unit_id", current.get("unit_id")))
    update: dict = {}
    field_map = {"event_date": "date"}
    for field in ("event_type", "event_date", "start_at", "end_at", "unit_id", "title", "notes"):
        if field not in patch:
            continue
        target = field_map.get(field, field)
        value = patch[field]
        if field in {"event_type", "event_date"} and not value:
            raise ValueError(f"{field} cannot be empty")
        if field == "event_type" and value:
            value = normalise_event_type(value)
        if field == "event_date" and value:
            value = str(value)
        update[target] = value

    requirements_marker = (
        "staffing_requirements" in patch or "event_type" in patch
    )
    if requirements_marker:
        event_type = update.get("event_type", current["event_type"])
        requirements = event_requirements_for(
            event_type, patch.get("staffing_requirements"))
        update["required_staffing_json"] = requirements
    if update:
        current = (client.table("facility_events").update(update)
                   .eq("facility_id", facility_id).eq("id", event_id)
                   .execute().data[0])

    if requirements_marker:
        (client.table("event_staffing_requirements").delete()
         .eq("facility_id", facility_id).eq("event_id", event_id).execute())
        saved = _insert_event_requirements(
            client, facility_id, event_id, requirements)
    else:
        saved = (client.table("event_staffing_requirements").select("*")
                 .eq("facility_id", facility_id).eq("event_id", event_id)
                 .execute().data)
    return _event_output(current, saved)


def delete_facility_event(client, facility_id: str, event_id: str) -> None:
    (client.table("facility_events").delete()
     .eq("facility_id", facility_id).eq("id", event_id).execute())


def _task_roster_violations(
    *,
    task_rows: list[dict],
    assignments_by_id: dict[str, dict],
    shifts_by_id: dict[str, dict],
    staff_by_id: dict[str, dict],
    task_by_id: dict[str, dict],
    qualification_rows: list[dict],
) -> list[dict]:
    violations: list[dict] = []
    qualification_cache: dict[str, dict[str, set[str]]] = {}
    for row in task_rows:
        task_assignment_id = _persisted_task_assignment_id(row.get("id"))
        task_reference = str(row.get("id") or "")
        assignment = assignments_by_id.get(row.get("shift_assignment_id"))
        if not assignment:
            continue
        shift = shifts_by_id.get(assignment.get("shift_id"))
        staff = staff_by_id.get(assignment.get("staff_id"))
        task = task_by_id.get(row.get("task_id"))
        if not shift or not staff:
            continue
        if not task:
            violations.append({
                "rule_code": "task_eligibility",
                "shift_id": shift["id"],
                "date": str(shift["date"])[:10],
                "unit_id": shift.get("unit_id"),
                "task_assignment_id": task_assignment_id,
                "severity": "hard",
                "message": f"Unknown task '{row.get('task_label')}'.",
                "details": {
                    "reason": "unknown_task",
                    "task_reference": task_reference,
                    "source_type": row.get("source_type"),
                },
                "resolved": False,
            })
            continue
        date_text = str(shift["date"])[:10]
        if date_text not in qualification_cache:
            qualification_cache[date_text] = _qualification_map_for_date(
                qualification_rows, date_text)
        issues = task_assignment_issues(
            task, staff,
            qualification_cache[date_text].get(staff["id"], set()), shift)
        if not issues:
            continue
        violations.append({
            "rule_code": "task_eligibility",
            "shift_id": shift["id"],
            "date": str(shift["date"])[:10],
            "unit_id": shift.get("unit_id"),
            "task_assignment_id": task_assignment_id,
            "severity": "hard",
            "message": (
                f"{row.get('task_label')} is not eligible for "
                f"{staff.get('name_en') or staff.get('name')}."
            ),
            "details": {
                "issues": issues,
                "task_id": task["id"],
                "task_reference": task_reference,
                "source_type": row.get("source_type"),
            },
            "resolved": False,
        })
    return violations


def _task_definitions_by_label(
    task_definitions: Iterable[dict],
    *,
    shift: dict,
    staff: dict,
) -> dict[str, dict]:
    """Resolve legacy labels using the same context preference as persistence."""
    task_by_label: dict[str, dict] = {}
    for task in task_definitions:
        matches_context = (
            task_rank_matches(staff.get("rank"), task.get("required_rank"))
            and (
                not task.get("shift_type")
                or task["shift_type"] == shift.get("shift_type")
            )
        )
        for label in (task.get("task_name"), task.get("task_code")):
            if label and (label not in task_by_label or matches_context):
                task_by_label[label] = task
    return task_by_label


def _reconciled_task_rows(
    *,
    task_rows: Iterable[dict],
    assignments: Iterable[dict],
    shifts_by_id: dict[str, dict],
    staff_by_id: dict[str, dict],
    task_definitions: list[dict],
) -> list[dict]:
    """Return the task rows validation would see after legacy reconciliation.

    This is deliberately in-memory. A read-only validation must not materialize
    ``shift_assignments.tasks`` into ``task_assignments`` or remove stale rows.
    """
    rows = [dict(row) for row in task_rows]
    for assignment in assignments:
        labels = list(assignment.get("tasks") or ())
        if not labels:
            continue
        shift = shifts_by_id.get(assignment.get("shift_id"))
        if not shift:
            continue
        assignment_id = assignment["id"]
        existing = [
            row for row in rows
            if row.get("shift_assignment_id") == assignment_id
        ]
        existing_labels = {
            row.get("task_label") for row in existing
            if row.get("task_label") in labels
        }
        rows = [
            row for row in rows
            if (
                row.get("shift_assignment_id") != assignment_id
                or row.get("task_label") in labels
            )
        ]
        task_by_label = _task_definitions_by_label(
            task_definitions,
            shift=shift,
            staff=staff_by_id.get(assignment.get("staff_id"), {}),
        )
        for index, label in enumerate(labels):
            if label in existing_labels:
                continue
            task = task_by_label.get(label)
            rows.append({
                "id": f"legacy:{assignment_id}:{index}",
                "shift_assignment_id": assignment_id,
                "staff_id": assignment.get("staff_id"),
                "task_id": task.get("id") if task else None,
                "task_label": label,
                "source_type": "legacy_cell",
            })
            existing_labels.add(label)
    return rows


def evaluate_roster_rules(
    *,
    shifts: Iterable[dict],
    assignments: Iterable[dict],
    staff: Iterable[dict],
    units: Iterable[dict],
    task_definitions: Iterable[dict],
    task_assignments: Iterable[dict],
    qualification_rows: Iterable[dict],
    events: Iterable[dict],
    event_requirements: Iterable[dict],
    floor_rules: Iterable[dict],
) -> list[dict]:
    """Pure Phase 4 validation over one immutable set of roster inputs."""
    shifts = list(shifts)
    assignments = list(assignments)
    staff = list(staff)
    units = list(units)
    task_definitions = list(task_definitions)
    shifts_by_id = {row["id"]: row for row in shifts}
    assignments_by_id = {row["id"]: row for row in assignments}
    staff_by_id = {row["id"]: row for row in staff}
    task_by_id = {row["id"]: row for row in task_definitions}
    reconciled_tasks = _reconciled_task_rows(
        task_rows=task_assignments,
        assignments=assignments,
        shifts_by_id=shifts_by_id,
        staff_by_id=staff_by_id,
        task_definitions=task_definitions,
    )

    violations = _task_roster_violations(
        task_rows=reconciled_tasks,
        assignments_by_id=assignments_by_id,
        shifts_by_id=shifts_by_id,
        staff_by_id=staff_by_id,
        task_by_id=task_by_id,
        qualification_rows=list(qualification_rows),
    )
    violations.extend(evaluate_event_staffing(
        events=list(events),
        requirements=list(event_requirements),
        shifts=shifts,
        assignments=assignments,
        staff_by_id=staff_by_id,
    ))
    violations.extend(evaluate_floor_coverage(
        rules=list(floor_rules),
        units=units,
        shifts=shifts,
        assignments=assignments,
        staff_by_id=staff_by_id,
    ))
    return violations


def validate_roster_rules(
    client,
    facility_id: str,
    roster_version_id: str,
    *,
    persist: bool = True,
) -> list[dict]:
    """Run all deterministic Phase 4 rules for one roster version."""
    versions = (client.table("roster_versions").select("id")
                .eq("facility_id", facility_id).eq("id", roster_version_id)
                .execute().data)
    if not versions:
        raise ValueError("roster version not found")

    shifts = (client.table("shifts").select("*")
              .eq("facility_id", facility_id)
              .eq("roster_version_id", roster_version_id).execute().data)
    shifts_by_id = {row["id"]: row for row in shifts}
    assignments = []
    if shifts_by_id:
        assignments = (client.table("shift_assignments").select("*")
                       .eq("facility_id", facility_id)
                       .in_("shift_id", list(shifts_by_id)).execute().data)
    staff = (client.table("staff").select("*")
             .eq("facility_id", facility_id).execute().data)
    staff_by_id = {row["id"]: row for row in staff}
    units = (client.table("facility_units").select("*")
             .eq("facility_id", facility_id).execute().data)

    task_defs = (client.table("task_definitions").select("*")
                 .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
                 .eq("active", True).execute().data)
    # Older roster cells store labels in shift_assignments.tasks. Materialize
    # them only for a persisted validation. The pure path reconciles an
    # equivalent view in memory and therefore performs no writes.
    if persist:
        from .tasks import sync_assignment_tasks

        for assignment in assignments:
            if assignment.get("tasks"):
                shift = shifts_by_id[assignment["shift_id"]]
                task_by_label = _task_definitions_by_label(
                    task_defs,
                    shift=shift,
                    staff=staff_by_id.get(assignment.get("staff_id"), {}),
                )
                sync_assignment_tasks(
                    client, facility_id, assignment, shift, task_by_label)
    task_rows = (client.table("task_assignments").select("*")
                 .eq("facility_id", facility_id)
                 .eq("roster_version_id", roster_version_id).execute().data)
    qualification_rows = []
    if staff_by_id:
        qualification_rows = (client.table("staff_qualifications").select("*")
                              .eq("facility_id", facility_id)
                              .in_("staff_id", list(staff_by_id))
                              .eq("is_active", True).execute().data)
    if shifts:
        date_from = min(str(row["date"])[:10] for row in shifts)
        date_to = max(str(row["date"])[:10] for row in shifts)
        events = (client.table("facility_events").select("*")
                  .eq("facility_id", facility_id)
                  .gte("date", date_from).lte("date", date_to).execute().data)
    else:
        events = []
    event_requirements = []
    if events:
        event_requirements = (client.table("event_staffing_requirements").select("*")
                              .eq("facility_id", facility_id)
                              .in_("event_id", [event["id"] for event in events])
                              .execute().data)
    violations = evaluate_roster_rules(
        shifts=shifts,
        assignments=assignments,
        staff=staff,
        units=units,
        task_definitions=task_defs,
        task_assignments=task_rows,
        qualification_rows=qualification_rows,
        events=events,
        event_requirements=event_requirements,
        floor_rules=(
            client.table("floor_min_staffing_rules").select("*")
            .eq("facility_id", facility_id).eq("active", True)
            .execute().data
        ),
    )

    if persist:
        (client.table("violation_log").delete()
         .eq("facility_id", facility_id)
         .eq("roster_version_id", roster_version_id)
         .in_("rule_code", list(PHASE4_RULE_CODES)).execute())
        _persist_violations(
            client, facility_id, roster_version_id, violations)
    return violations
