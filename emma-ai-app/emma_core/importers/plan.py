"""What a parsed roster workbook looks like before it touches the database.

The layout readers produce a :class:`ParsedRoster`: plain dataclasses describing
the staff, the staff × day cells, the events row and everything the parser could
not resolve. Nothing here knows about Postgres, which is what lets the same
parse run as a dry-run validation (Phase 1.4's "validation summary") and as the
input to a commit.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date

from .cells import CellIntent
from .vocab import FacilityProfile


@dataclass(frozen=True)
class Issue:
    """One thing a human should look at, anchored to its source cell."""

    code: str
    message: str
    severity: str = "warning"        # info|warning|error
    sheet: str | None = None
    cell_ref: str | None = None
    raw_value: str | None = None

    def as_row(self) -> dict:
        return {
            "severity": self.severity, "code": self.code, "message": self.message,
            "sheet": self.sheet, "cell_ref": self.cell_ref,
            "raw_value": self.raw_value,
        }


@dataclass
class ParsedStaff:
    """One roster row's staff member.

    ``key`` is the identity within the workbook - Home A anonymises its staff as
    ``RCW12`` while Home B writes real names, and both are stable across the
    before/after sheet pair.
    """

    key: str
    display_name: str
    rank: str
    employment_type: str
    sheet: str
    row: int
    label: str | None = None
    unit_name: str | None = None
    is_relief_pool: bool = False
    contracted_hours: float | None = None
    # Cycle totals the homes keep in the trailing summary columns. The carried
    # compensatory hours seed the staff member's opening CL balance, so an
    # imported roster starts from the entitlement the home actually recorded.
    rest_days_total: int | None = None
    carried_cl_hours: float | None = None


@dataclass
class ParsedCell:
    """One staff member's one day."""

    staff_key: str
    date: Date
    intent: CellIntent
    sheet: str
    cell_ref: str
    unit_name: str | None = None
    extra_tasks: tuple[str, ...] = ()
    relief_name: str | None = None       # 替假 row: who actually covered


@dataclass
class ParsedEvent:
    """A facility event from the sheet's events row."""

    date: Date
    title: str
    markers: tuple[str, ...] = ()
    raw: str = ""


@dataclass
class ParsedRoster:
    """A whole workbook, parsed. The loader's only input."""

    facility_code: str
    profile: FacilityProfile
    layout: str
    source_name: str
    period_start: Date
    period_end: Date
    dates: list[Date] = field(default_factory=list)
    staff: list[ParsedStaff] = field(default_factory=list)
    cells: list[ParsedCell] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    request_quota: dict[Date, int] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def working_cells(self) -> list[ParsedCell]:
        return [c for c in self.cells if c.intent.is_working]

    @property
    def leave_cells(self) -> list[ParsedCell]:
        return [c for c in self.cells if c.intent.leave]

    def summary(self) -> dict:
        """The counts the import's validation summary reports."""
        shift_types = Counter(
            d.shift_code for c in self.cells for d in c.intent.duties)
        leave_types = Counter(
            c.intent.leave.code for c in self.leave_cells)
        return {
            "facility_code": self.facility_code,
            "layout": self.layout,
            "source_name": self.source_name,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "days": len(self.dates),
            "staff_rows": len(self.staff),
            "cells_parsed": len(self.cells),
            "working_cells": len(self.working_cells),
            "leave_cells": len(self.leave_cells),
            "staff_requests": sum(1 for c in self.cells if c.intent.is_request),
            "task_coded_cells": sum(1 for c in self.cells if c.intent.task_codes),
            "standing_duty_cells": sum(1 for c in self.cells if c.extra_tasks),
            "floor_scoped_cells": sum(1 for c in self.cells if c.unit_name),
            "relief_named_cells": sum(1 for c in self.cells if c.relief_name),
            "overtime_minutes": sum(c.intent.ot_minutes for c in self.cells),
            "compensatory_minutes": sum(c.intent.cl_minutes for c in self.cells),
            "events": len(self.events),
            "request_quota_days": len(self.request_quota),
            "shift_type_counts": dict(sorted(shift_types.items())),
            "leave_type_counts": dict(sorted(leave_types.items())),
            "issues": len(self.issues),
            "issues_by_severity": dict(Counter(i.severity for i in self.issues)),
        }
