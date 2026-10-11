"""Offline contract tests for the authoritative task-assignment draft gate.

The in-memory client deliberately models the complete minimal join path:
facility -> roster version -> shift -> shift assignment -> task assignment.
No test client, database, or URL is used; any fixture URL added in future must use
``https://test.invalid`` so this suite remains safely offline.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routers import scheduling as scheduling_router
from emma_core.models import EscortLocationAssign, TaskAssignmentCreate, TaskAssignmentPatch
from emma_core.services import scheduling as scheduling_svc
from emma_core.services.organisations import _ORG_BY_FACILITY


FACILITY_ID = "facility-a"
FOREIGN_FACILITY_ID = "facility-b"
ORG_ID = "org-a"
VERSION_ID = "version-1"
SHIFT_ID = "shift-1"
ASSIGNMENT_ID = "assignment-1"
STAFF_ID = "staff-1"
TASK_ID = "task-1"
TASK_ASSIGNMENT_ID = "task-assignment-1"


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    """Small, deterministic subset of the PostgREST chain used by these paths."""

    def __init__(self, client: "_MemoryClient", name: str):
        self.client = client
        self.name = name
        self.filters: list[tuple[str, object]] = []
        self.in_filters: list[tuple[str, set[object]]] = []
        self.operation = "select"
        self.payload = None
        self.sort_key = None

    def select(self, _columns="*"):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.in_filters.append((key, set(values)))
        return self

    def or_(self, _expression):
        # All dictionary rows in this fixture already belong to the test org.
        return self

    def order(self, key, desc=False):
        self.sort_key = (key, desc)
        return self

    def limit(self, _count):
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = deepcopy(payload)
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = deepcopy(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def _matches(self, row):
        return (all(row.get(key) == value for key, value in self.filters)
                and all(row.get(key) in values for key, values in self.in_filters))

    def execute(self):
        rows = self.client.rows.setdefault(self.name, [])
        matched = [row for row in rows if self._matches(row)]
        if self.operation == "select":
            data = deepcopy(matched)
            if self.sort_key:
                key, desc = self.sort_key
                data.sort(key=lambda row: (row.get(key) is None, row.get(key)), reverse=desc)
            return _Result(data)

        self.client.writes.append((self.operation, self.name, deepcopy(self.payload)))
        if self.operation == "update":
            for row in matched:
                row.update(deepcopy(self.payload))
            return _Result(deepcopy(matched))
        if self.operation == "delete":
            self.client.rows[self.name] = [row for row in rows if not self._matches(row)]
            return _Result(deepcopy(matched))

        payload_rows = self.payload if isinstance(self.payload, list) else [self.payload]
        inserted = []
        for payload in payload_rows:
            row = deepcopy(payload)
            generated_id = (
                TASK_ASSIGNMENT_ID if self.name == "task_assignments"
                else f"{self.name}-{len(rows) + 1}"
            )
            row.setdefault("id", generated_id)
            rows.append(row)
            inserted.append(row)
        return _Result(deepcopy(inserted))


class _MemoryClient:
    def __init__(self, version_state: str = "draft"):
        version = {"id": VERSION_ID, "facility_id": FACILITY_ID, "status": "draft"}
        if version_state == "published":
            version["status"] = "published"
        elif version_state == "foreign":
            version["facility_id"] = FOREIGN_FACILITY_ID
        elif version_state == "missing":
            version = None
        self.rows = {
            "facilities": [{"id": FACILITY_ID, "org_id": ORG_ID}],
            "roster_versions": [version] if version else [],
            "shifts": [{
                "id": SHIFT_ID,
                "facility_id": FACILITY_ID,
                "roster_version_id": VERSION_ID,
                "date": "2026-10-11",
                "shift_type": "A",
                "unit_id": None,
            }],
            "shift_assignments": [{
                "id": ASSIGNMENT_ID,
                "facility_id": FACILITY_ID,
                "shift_id": SHIFT_ID,
                "staff_id": STAFF_ID,
                "tasks": ["Morning medicine"],
            }],
            "staff": [{
                "id": STAFF_ID,
                "facility_id": FACILITY_ID,
                "rank": "HW",
                "employment_type": "local_ft",
            }],
            "task_definitions": [{
                "id": TASK_ID,
                "org_id": ORG_ID,
                "active": True,
                "task_code": "A1",
                "task_name": "Morning medicine",
                "required_rank": "HW",
                "shift_type": "A",
                "needs_location": False,
            }],
            "shift_definitions": [{"org_id": ORG_ID, "shift_type": "A"}],
            "staff_qualifications": [],
            "escort_locations": [{
                "id": "escort-location-1",
                "org_id": ORG_ID,
                "code": "TMH",
                "active": True,
            }],
            "task_assignments": [{
                "id": TASK_ASSIGNMENT_ID,
                "facility_id": FACILITY_ID,
                "roster_version_id": VERSION_ID,
                "shift_assignment_id": ASSIGNMENT_ID,
                "staff_id": STAFF_ID,
                "task_id": TASK_ID,
                "task_label": "Morning medicine",
                "source_type": "manual",
                "task_status": "pending",
            }],
        }
        self.writes: list[tuple[str, str, object]] = []

    def table(self, name):
        return _Table(self, name)


@pytest.fixture(autouse=True)
def _clear_org_cache():
    # org_id_for is intentionally process-cached in production. Clearing it makes
    # every test prove its own full facility fixture rather than inherit another.
    _ORG_BY_FACILITY.clear()
    yield
    _ORG_BY_FACILITY.clear()


def _payload():
    return {"shift_assignment_id": ASSIGNMENT_ID, "task_id": TASK_ID}


def _invoke(service_client: _MemoryClient, operation: str):
    if operation == "create":
        return scheduling_svc.create_task_assignment(
            service_client, FACILITY_ID, _payload())
    if operation == "update":
        return scheduling_svc.update_task_assignment(
            service_client, FACILITY_ID, TASK_ASSIGNMENT_ID,
            {"start_at": "2026-10-11T08:00:00"})
    if operation == "delete":
        return scheduling_svc.delete_task_assignment(
            service_client, FACILITY_ID, TASK_ASSIGNMENT_ID)
    if operation == "escort-location":
        return scheduling_svc.set_task_assignment_escort_location(
            service_client, FACILITY_ID, TASK_ASSIGNMENT_ID, location="TMH")
    if operation == "synchronize":
        return scheduling_svc.sync_task_rows_for_assignment(
            service_client, FACILITY_ID, ASSIGNMENT_ID)
    raise AssertionError(f"unknown operation {operation}")


@pytest.mark.parametrize("operation", [
    "create", "update", "delete", "escort-location", "synchronize",
])
@pytest.mark.parametrize("version_state, expected_code", [
    ("published", "roster_locked"),
    ("missing", "roster_version_not_found"),
    ("foreign", "roster_version_not_found"),
])
def test_every_task_mutation_refuses_non_draft_or_out_of_scope_roster(
        operation, version_state, expected_code):
    client = _MemoryClient(version_state)

    with pytest.raises(scheduling_svc.TaskAssignmentDraftError) as caught:
        _invoke(client, operation)

    assert caught.value.code == expected_code
    assert client.writes == [], f"{operation} wrote despite {version_state} roster"


def test_draft_task_lifecycle_allows_create_update_escort_and_delete():
    client = _MemoryClient()
    # Start without a row so this proves create is not merely a guarded upsert.
    client.rows["task_assignments"] = []

    created = _invoke(client, "create")
    assert created["roster_version_id"] == VERSION_ID
    assert created["shift_assignment_id"] == ASSIGNMENT_ID

    updated = _invoke(client, "update")
    assert updated["start_at"] == "2026-10-11T08:00:00"

    escorted = _invoke(client, "escort-location")
    assert escorted["escort_location"] == "TMH"
    assert escorted["escort_location_id"] == "escort-location-1"

    assert _invoke(client, "delete") is None
    assert client.rows["task_assignments"] == []
    assert client.rows["shift_assignments"][0]["tasks"] == []


def test_task_row_cannot_claim_a_different_roster_version():
    client = _MemoryClient()
    client.rows["task_assignments"][0]["roster_version_id"] = "other-version"

    with pytest.raises(scheduling_svc.TaskAssignmentDraftError) as caught:
        _invoke(client, "escort-location")

    assert caught.value.code == "roster_version_not_found"
    assert client.writes == []


def test_foreign_shift_assignment_is_hidden_before_any_task_write():
    client = _MemoryClient()
    client.rows["shift_assignments"][0]["facility_id"] = FOREIGN_FACILITY_ID

    with pytest.raises(ValueError, match="shift assignment not found"):
        _invoke(client, "create")

    assert client.writes == []


@pytest.mark.parametrize("operation", [
    "create", "update", "delete", "escort-location",
])
def test_router_maps_published_draft_guard_to_roster_locked_without_relaxing_rbac(
        operation):
    client = _MemoryClient("published")
    ctx = SimpleNamespace(
        client=client,
        facility_id=FACILITY_ID,
        profile=SimpleNamespace(role="scheduler"),
    )

    handlers = {
        "create": lambda: scheduling_router.create_task_assignment(
            TaskAssignmentCreate(**_payload()), ctx),
        "update": lambda: scheduling_router.update_task_assignment(
            TASK_ASSIGNMENT_ID,
            TaskAssignmentPatch(start_at="2026-10-11T08:00:00"), ctx),
        "delete": lambda: scheduling_router.delete_task_assignment(
            TASK_ASSIGNMENT_ID, ctx),
        "escort-location": lambda: scheduling_router.set_escort_location(
            TASK_ASSIGNMENT_ID, EscortLocationAssign(escort_location="TMH"), ctx),
    }
    with pytest.raises(HTTPException) as caught:
        handlers[operation]()

    assert caught.value.status_code == 409
    assert caught.value.detail == {
        "code": "roster_locked", "message": "Only a draft roster may be edited.",
    }
    assert client.writes == []


def test_router_maps_missing_version_escort_guard_to_not_found():
    client = _MemoryClient("missing")
    ctx = SimpleNamespace(
        client=client,
        facility_id=FACILITY_ID,
        profile=SimpleNamespace(role="scheduler"),
    )

    with pytest.raises(HTTPException) as caught:
        scheduling_router.set_escort_location(
            TASK_ASSIGNMENT_ID, EscortLocationAssign(escort_location="TMH"), ctx)

    assert caught.value.status_code == 404
    assert caught.value.detail == {
        "code": "not_found", "message": "roster version not found",
    }
    assert client.writes == []
