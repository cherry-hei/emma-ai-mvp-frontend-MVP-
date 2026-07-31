"""Service-layer tests against the seeded local DB (service-role client)."""
from datetime import date, timedelta

from emma_core.db import get_service_client
from emma_core.services.auth import get_profile, sign_in
from emma_core.services.compliance import compute_ratios
from emma_core.services.residents import get_units, set_resident_count
from emma_core.services.roster import (
    clear_cell, get_roster_grid, get_shift_defs, set_cell,
)

sb = get_service_client()


def _facility(code: str) -> str:
    # SQL: select id from facilities where code = :code
    return sb.table("facilities").select("id").eq("code", code).execute().data[0]["id"]


def test_roster_grid_shape():
    """The grid is a rectangle of staff x the period's days, with real cells in it.

    Asserted as invariants rather than fixture counts: Home A's cycle is 28 days
    under either fixture, but the number of staff and who works day 0 belong to
    the data, not to the contract.
    """
    grid = get_roster_grid(sb, _facility("A"))
    assert grid.version_id and grid.status == "draft"
    assert grid.rows, "the grid should carry the facility's staff"
    assert len(grid.dates) == 28                  # Home A rosters a 28-day cycle
    # Every row is aligned to the same date axis - the UI indexes cells by column.
    for row in grid.rows:
        assert [c.date for c in row.cells] == grid.dates
    working = [c for row in grid.rows for c in row.cells if c.is_working]
    assert working, "a rostered period should contain working cells"
    assert all(c.shift_type and c.assignment_id for c in working)
    assert any(c.tasks for row in grid.rows for c in row.cells), (
        "the roster should carry task labels on at least one cell")


def test_shift_defs_present():
    defs = get_shift_defs(sb, _facility("A"))
    codes = {d.shift_type for d in defs}
    assert {"A", "P", "N", "AN", "OFF", "AL", "SLEEP"} <= codes


def test_ratio_computation():
    res = compute_ratios(sb, _facility("A"), date(2026, 7, 1))
    assert res
    rn = next(r for r in res if r.rank == "RN")
    assert rn.residents == 18          # 10 East + 8 West
    # Phase 5 compares equivalent-head capacity before rounding, so a 1:60 rule
    # reports 18/60 rather than ceil(). That is what lets a fractional rank
    # substitution (Home B: one HW carries 40/60 of RN/EN capacity) be expressed.
    assert rn.required == 0.3
    assert rn.actual >= 0


def test_auth_sign_in_and_profile():
    client, session = sign_in("super_a@emma.local", "EmmaDev123!")
    prof = get_profile(client, session.user.id)
    assert prof and prof.role == "superintendent"
    assert prof.facility.code == "A"


def test_set_and_clear_cell_write_path():
    fid = _facility("A")
    grid = get_roster_grid(sb, fid)
    ver, staff_id = grid.version_id, grid.rows[0].staff.id
    defs = {d.shift_type: d for d in get_shift_defs(sb, fid)}
    # Derive a day past the end of the rostered cycle rather than hardcoding one:
    # clearing the edit must remove the cell outright, which only holds where no
    # seeded shift sits underneath, and the current cycle rolls with the calendar.
    last_day = max(c.date for r in grid.rows for c in r.cells)
    day = (last_day + timedelta(days=7)).isoformat()

    set_cell(sb, facility_id=fid, roster_version_id=ver, staff_id=staff_id,
             date=day, shift_type="P", shift_def=defs["P"], tasks=["Test task"])
    g2 = get_roster_grid(sb, fid)
    row = next(r for r in g2.rows if r.staff.id == staff_id)
    cell = next((c for c in row.cells if c.date.isoformat() == day), None)
    assert cell and cell.shift_type == "P" and cell.tasks == ["Test task"]

    # SQL: select id from manual_override_log where roster_version_id = :ver
    logs = (sb.table("manual_override_log").select("id")
            .eq("roster_version_id", ver).execute().data)
    assert len(logs) >= 1  # edit was audited

    clear_cell(sb, facility_id=fid, roster_version_id=ver, staff_id=staff_id, date=day)
    g3 = get_roster_grid(sb, fid)
    row3 = next(r for r in g3.rows if r.staff.id == staff_id)
    assert all(c.date.isoformat() != day for c in row3.cells)


def test_resident_count_feeds_ratio():
    fid = _facility("A")
    units = {u.name: u.id for u in get_units(sb, fid)}
    east = units["East Wing"]
    set_resident_count(sb, facility_id=fid, date="2026-07-02", unit_id=east,
                       care_level="general", count=100)
    res = compute_ratios(sb, fid, date(2026, 7, 2))
    rn = next(r for r in res if r.rank == "RN")
    assert rn.residents == 108  # 100 East + 8 West
    set_resident_count(sb, facility_id=fid, date="2026-07-02", unit_id=east,
                       care_level="general", count=10)  # restore
