"""Service-layer tests against the seeded local DB (service-role client)."""
from datetime import date

from emma_core.db import get_service_client
from emma_core.services.auth import get_profile, sign_in
from emma_core.services.compliance import compute_ratios
from emma_core.services.residents import get_units, set_resident_count
from emma_core.services.roster import (
    clear_cell, get_roster_grid, get_shift_defs, set_cell,
)
from emma_web.state import rows_from_grid

sb = get_service_client()


def _facility(code: str) -> str:
    return sb.table("facilities").select("id").eq("code", code).execute().data[0]["id"]


def test_roster_grid_shape():
    grid = get_roster_grid(sb, _facility("A"))
    assert grid.version_id and grid.status == "draft"
    assert len(grid.rows) == 7
    assert len(grid.dates) == 7
    rn = next(r for r in grid.rows if r.staff.rank == "RN")
    en = next(r for r in grid.rows if r.staff.rank == "EN")
    assert rn.cells[0].shift_type == "P" and rn.cells[0].is_working
    assert en.cells[0].shift_type == "OFF" and not en.cells[0].is_working
    assert rn.cells[0].tasks  # day-0 task labels present


def test_shift_defs_present():
    defs = get_shift_defs(sb, _facility("A"))
    codes = {d.shift_type for d in defs}
    assert {"A", "P", "N", "AN", "OFF", "AL", "SLEEP"} <= codes


def test_ratio_computation():
    res = compute_ratios(sb, _facility("A"), date(2026, 7, 1))
    assert res
    rn = next(r for r in res if r.rank == "RN")
    assert rn.residents == 80          # 42 East + 38 West
    assert rn.required == 2            # ceil(80/60)
    assert rn.actual >= 0


def test_auth_sign_in_and_profile():
    client, session = sign_in("super_a@emma.local", "EmmaDev123!")
    prof = get_profile(client, session.user.id)
    assert prof and prof.role == "superintendent"
    assert prof.facility.code == "A"


def test_rows_from_grid_view_models():
    grid = get_roster_grid(sb, _facility("A"))
    rows = rows_from_grid(grid)
    assert len(rows) == 7
    rn = next(r for r in rows if r.subtitle.startswith("RN"))
    assert len(rn.cells) == len(grid.dates)
    assert rn.cells[0].label == "P" and rn.cells[0].bg  # working cell is coloured
    off = next(c for r in rows for c in r.cells if c.label == "OFF")
    assert off.bg  # non-working cells styled too


def test_set_and_clear_cell_write_path():
    fid = _facility("A")
    grid = get_roster_grid(sb, fid)
    ver, staff_id = grid.version_id, grid.rows[0].staff.id
    defs = {d.shift_type: d for d in get_shift_defs(sb, fid)}
    day = "2026-07-15"  # outside the seeded demo week

    set_cell(sb, facility_id=fid, roster_version_id=ver, staff_id=staff_id,
             date=day, shift_type="P", shift_def=defs["P"], tasks=["Test task"])
    g2 = get_roster_grid(sb, fid)
    row = next(r for r in g2.rows if r.staff.id == staff_id)
    cell = next((c for c in row.cells if c.date.isoformat() == day), None)
    assert cell and cell.shift_type == "P" and cell.tasks == ["Test task"]

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
    assert rn.residents == 138  # 100 East + 38 West
    set_resident_count(sb, facility_id=fid, date="2026-07-02", unit_id=east,
                       care_level="general", count=42)  # restore
