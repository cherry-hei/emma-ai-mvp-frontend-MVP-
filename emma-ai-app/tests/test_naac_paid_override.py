"""Regression coverage for authoritative NAAC paid minutes during roster import.

The fixture is deliberately a fake PostgREST client: this verifies importer payloads
without a database, migration, or source-workbook write.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from emma_core.importers import loader, naac
from emma_core.importers.cells import parse_cell
from emma_core.importers.plan import ParsedCell, ParsedRoster, ParsedStaff
from emma_core.services.validation import RosterSnapshot, evaluate_core_constraints


class FakeQuery:
    """Minimal fluent query object for the two loader paths under test."""

    def __init__(self, client: "FakeLoader", table: str):
        self.client = client
        self.table_name = table
        self.action = "select"
        self.filters: list[tuple[str, object]] = []
        self.payload = None

    def select(self, _columns: str = "*") -> "FakeQuery":
        return self

    def eq(self, column: str, value) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def insert(self, payload) -> "FakeQuery":
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "select":
            rows = self.client.rows.get(self.table_name, [])
            return SimpleNamespace(data=[
                deepcopy(row) for row in rows
                if all(row.get(column) == value for column, value in self.filters)
            ])

        rows = self.payload if isinstance(self.payload, list) else [self.payload]
        written = []
        for row in rows:
            stored = deepcopy(row)
            stored.setdefault("id", f"{self.table_name}-{len(self.client.inserted[self.table_name]) + 1}")
            self.client.inserted[self.table_name].append(stored)
            written.append({"id": stored["id"]})
        return SimpleNamespace(data=written)


class FakeLoader:
    """In-memory capture of loader reads and writes; it never contacts Supabase."""

    def __init__(self):
        self.rows = {
            "facilities": [{"id": "facility-1", "org_id": "org-1"}],
            "shift_definitions": [],
        }
        self.inserted: dict[str, list[dict]] = {
            "shift_definitions": [],
            "shifts": [],
            "shift_assignments": [],
            "task_assignments": [],
        }

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def _parsed_naac_roster() -> ParsedRoster:
    profile = naac.profile()
    on_date = date(2026, 8, 3)
    codes = ("P1C#", "A7#", "A2s#")
    return ParsedRoster(
        facility_code="NAAC",
        profile=profile,
        layout="fake",
        source_name="fake-naac-paid-minutes",
        period_start=on_date,
        period_end=on_date,
        dates=[on_date],
        staff=[ParsedStaff(
            key="staff-1", display_name="Fake staff", rank="PCW",
            employment_type="local_ft", sheet="tahduty", row=1,
        )],
        cells=[ParsedCell(
            staff_key="staff-1", date=on_date,
            intent=parse_cell(code, profile), sheet="tahduty", cell_ref=f"A{index + 1}",
        ) for index, code in enumerate(codes)],
    )


def test_naac_source_paid_minutes_reach_definitions_shifts_and_weekly_validation():
    """The NAAC 時數 column wins even when a duty has no parseable clock window."""
    client = FakeLoader()
    parsed = _parsed_naac_roster()
    result = loader.LoadResult(mode="commit", facility_id="facility-1")
    expected = {
        code: naac.load_shift_codes()[code].paid_minutes
        for code in ("P1C#", "A7#", "A2s#")
    }

    # The source's compound/sleepover description cannot be represented as a
    # normal clock window, which was the path that previously lost its 12 hours.
    p1c_window = next(w for w in parsed.profile.shift_windows if w.code == "P1C#")
    assert (p1c_window.start, p1c_window.end, p1c_window.segments) == (None, None, ())
    assert expected == {"P1C#": 720, "A7#": 480, "A2s#": 510}

    loader._ensure_shift_definitions(client, "facility-1", parsed, result, write=True)
    definitions = {
        row["shift_type"]: row["paid_minutes"]
        for row in client.inserted["shift_definitions"]
        if row["shift_type"] in expected
    }
    assert definitions == expected

    loader._write_cells(
        client, "facility-1", parsed, "roster-version-1", {"staff-1": "staff-1"},
        {}, loader.TaskDictionary([]), result,
    )
    persisted = {
        row["shift_type"]: row["paid_minutes"]
        for row in client.inserted["shifts"]
    }
    assert persisted == expected

    p1c_shift = next(row for row in client.inserted["shifts"] if row["shift_type"] == "P1C#")
    snapshot = RosterSnapshot(
        facility_id="facility-1",
        roster_version_id="roster-version-1",
        period_id="period-1",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 3),
        facility={"id": "facility-1", "code": "NAAC"},
        shifts=(p1c_shift,),
        assignments=({
            "id": "assignment-1", "shift_id": p1c_shift["id"], "staff_id": "staff-1",
            "role": "PCW", "status": "assigned",
        },),
        staff=({"id": "staff-1", "rank": "PCW", "employment_type": "local_ft"},),
        contracts=({
            "staff_id": "staff-1", "max_weekly_hours": 11,
            "effective_from": "2026-01-01",
        },),
    )
    max_hours = [
        finding for finding in evaluate_core_constraints(snapshot)
        if finding["rule_code"] == "max_hours"
    ]
    assert len(max_hours) == 1
    assert max_hours[0]["details"]["actual_minutes"] == 720
