"""Data preconditions for the DB-backed tests.

The database can legitimately hold either of two fixtures, and they carry
different things:

``scripts/seed.py``
    Generated demo data - 7 patterned Home A staff plus a full operations layer
    (certificates, SL incidents, agency spend, attendance, notifications).
``scripts/import_real_rosters.py``
    The homes' real rosters - 48 Home A staff over a real 28-day cycle, with real
    task codes, leave and events, but none of the operations layer, because a
    roster spreadsheet does not record incidents, agency invoices or clock-ins.

A DB-backed test therefore states the data it needs and skips - loudly, naming
the missing data - when the database does not have it, exactly as it already
skips when no database is reachable. What it must not do is assert a fixture's
magic numbers: `len(staff) == 7` tests the seed, not the system.
"""
from __future__ import annotations

import pytest


def require(rows, what: str):
    """Return `rows`, or skip the test naming the data the database lacks."""
    if not rows:
        pytest.skip(f"this database holds no {what}")
    return rows


def require_count(value: float, what: str, *, minimum: float = 1):
    if value is None or value < minimum:
        pytest.skip(f"this database holds no {what}")
    return value
