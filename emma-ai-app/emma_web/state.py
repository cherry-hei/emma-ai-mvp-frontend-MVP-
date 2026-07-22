"""Reflex state for the Emma AI manager dashboard.

Event handlers run server-side in Python, so they call emma_core services
directly. State holds display-ready view-models (formatting done here, not in
templates) to keep the component tree free of Var string-ops.
"""
from __future__ import annotations

import dataclasses

import reflex as rx

from emma_core.config import settings
from emma_core.constants import DEFAULT_STYLE, SHIFT_STYLE, RosterStatus
from emma_core.db import get_user_client
from emma_core.services.auth import get_profile, sign_in
from emma_core.services.compliance import compute_ratios
from emma_core.services.residents import get_units, set_resident_count
from emma_core.services.roster import (
    clear_cell, get_roster_grid, get_shift_defs, publish_version, set_cell,
)

DEV_PASSWORD = "EmmaDev123!"


@dataclasses.dataclass
class CellVM:
    label: str = ""
    bg: str = ""
    fg: str = ""
    staff_id: str = ""
    staff_name: str = ""
    date: str = ""
    tasks: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class RowVM:
    staff_id: str = ""
    staff_name: str = ""
    subtitle: str = ""
    cells: list[CellVM] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class RatioVM:
    label: str = ""
    count_label: str = ""
    verdict: str = ""
    ok: bool = True


def rows_from_grid(grid) -> list[RowVM]:
    """Map a RosterGrid (domain) into display-ready view-models."""
    rows: list[RowVM] = []
    for r in grid.rows:
        cells: list[CellVM] = []
        for c in r.cells:
            code = c.shift_type or ""
            bg, fg = SHIFT_STYLE.get(code, DEFAULT_STYLE) if code else ("", "")
            cells.append(CellVM(label=code, bg=bg, fg=fg, tasks=c.tasks,
                                staff_id=r.staff.id, staff_name=r.staff.name,
                                date=c.date.isoformat()))
        subtitle = str(r.staff.rank) + (f" · {r.staff.unit_name}" if r.staff.unit_name else "")
        rows.append(RowVM(staff_id=r.staff.id, staff_name=r.staff.name,
                          subtitle=subtitle, cells=cells))
    return rows


class AppState(rx.State):
    # ── auth ──
    error: str = ""
    token: str = ""
    user_id: str = ""
    profile_id: str = ""
    role: str = ""
    facility_id: str = ""
    facility_name: str = ""

    # ── roster ──
    version_id: str = ""
    status: str = ""
    period_label: str = ""
    ratio_date: str = ""
    dates: list[str] = []
    rows: list[RowVM] = []
    ratios: list[RatioVM] = []
    shift_types: list[str] = []
    unit_names: list[str] = []

    # ── shift editor dialog ──
    dialog_open: bool = False
    edit_staff_id: str = ""
    edit_staff_name: str = ""
    edit_date: str = ""
    edit_shift_type: str = ""
    edit_tasks: str = ""

    # ── resident-count input ──
    resident_unit_name: str = ""
    resident_count_str: str = "0"

    # ── computed ──
    @rx.var
    def logged_in(self) -> bool:
        return bool(self.token)

    @rx.var
    def is_published(self) -> bool:
        return self.status == RosterStatus.PUBLISHED

    @rx.var
    def is_dev(self) -> bool:
        return settings.app_env == "development"

    def _client(self):
        return get_user_client(self.token)

    # ── auth events ──
    def _do_login(self, email: str, password: str):
        self.error = ""
        try:
            client, session = sign_in(email, password)
            prof = get_profile(client, session.user.id)
        except Exception:
            self.error = "Login failed — check email and password."
            return None
        if not prof:
            self.error = "No profile is linked to this account."
            return None
        self.token = session.access_token
        self.user_id = session.user.id
        self.profile_id = prof.id
        self.role = str(prof.role)
        self.facility_id = prof.facility_id or ""
        self.facility_name = prof.facility.name if prof.facility else ""
        return rx.redirect("/roster")

    @rx.event
    def login(self, form_data: dict):
        return self._do_login(form_data.get("email", ""), form_data.get("password", ""))

    @rx.event
    def dev_login(self, email: str):
        """Dev-only server-side sign-in (no credential typed into the UI)."""
        return self._do_login(email, DEV_PASSWORD)

    @rx.event
    def logout(self):
        self.token = ""
        self.role = ""
        self.rows = []
        self.ratios = []
        return rx.redirect("/")

    # ── roster load / refresh ──
    @rx.event
    def load_roster(self):
        if not self.token:
            return rx.redirect("/")
        client = self._client()
        self.shift_types = [d.shift_type for d in get_shift_defs(client, self.facility_id)]
        self.unit_names = [u.name for u in get_units(client, self.facility_id)]
        if self.unit_names and not self.resident_unit_name:
            self.resident_unit_name = self.unit_names[0]

        grid = get_roster_grid(client, self.facility_id)
        self.version_id = grid.version_id or ""
        if grid.period_start and grid.period_end:
            self.period_label = f"{grid.period_start:%d %b} – {grid.period_end:%d %b %Y}"
        self.ratio_date = grid.dates[0].isoformat() if grid.dates else ""
        self._apply_grid(grid)
        self._load_ratios(client)

    def _apply_grid(self, grid) -> None:
        self.status = grid.status or ""
        self.dates = [d.strftime("%a %d/%m") for d in grid.dates]
        self.rows = rows_from_grid(grid)

    def _refresh(self, client) -> None:
        self._apply_grid(get_roster_grid(client, self.facility_id))
        self._load_ratios(client)

    def _load_ratios(self, client) -> None:
        if not self.ratio_date:
            self.ratios = []
            return
        self.ratios = [
            RatioVM(label=x.label, count_label=f"{x.actual}/{x.required}",
                    verdict="OK" if x.passes else "SHORT", ok=x.passes)
            for x in compute_ratios(client, self.facility_id, self.ratio_date)
        ]

    # ── shift editor ──
    @rx.event
    def open_editor(self, staff_id: str, staff_name: str, date: str, label: str, tasks: list[str]):
        self.edit_staff_id = staff_id
        self.edit_staff_name = staff_name
        self.edit_date = date
        self.edit_shift_type = label or (self.shift_types[0] if self.shift_types else "")
        self.edit_tasks = ", ".join(tasks) if tasks else ""
        self.dialog_open = True

    @rx.event
    def set_dialog(self, value: bool):
        self.dialog_open = value

    @rx.event
    def set_edit_shift_type(self, value: str):
        self.edit_shift_type = value

    @rx.event
    def set_edit_tasks(self, value: str):
        self.edit_tasks = value

    @rx.event
    def save_cell(self):
        if not self.version_id or not self.edit_shift_type:
            self.dialog_open = False
            return
        client = self._client()
        defs = {d.shift_type: d for d in get_shift_defs(client, self.facility_id)}
        sd = defs.get(self.edit_shift_type)
        if not sd:
            self.dialog_open = False
            return
        tasks = [t.strip() for t in self.edit_tasks.split(",") if t.strip()]
        set_cell(client, facility_id=self.facility_id, roster_version_id=self.version_id,
                 staff_id=self.edit_staff_id, date=self.edit_date,
                 shift_type=self.edit_shift_type, shift_def=sd, tasks=tasks,
                 changed_by=self.profile_id)
        self.dialog_open = False
        self._refresh(client)

    @rx.event
    def clear_current(self):
        if not self.version_id:
            self.dialog_open = False
            return
        client = self._client()
        clear_cell(client, facility_id=self.facility_id, roster_version_id=self.version_id,
                   staff_id=self.edit_staff_id, date=self.edit_date, changed_by=self.profile_id)
        self.dialog_open = False
        self._refresh(client)

    # ── resident count ──
    @rx.event
    def set_resident_unit_name(self, value: str):
        self.resident_unit_name = value

    @rx.event
    def set_resident_count_str(self, value: str):
        self.resident_count_str = value

    @rx.event
    def save_resident_count(self):
        if not self.ratio_date or not self.resident_unit_name:
            return
        try:
            count = int(self.resident_count_str)
        except ValueError:
            return
        client = self._client()
        units = get_units(client, self.facility_id)
        uid = next((u.id for u in units if u.name == self.resident_unit_name), None)
        if not uid:
            return
        set_resident_count(client, facility_id=self.facility_id, date=self.ratio_date,
                           unit_id=uid, care_level="general", count=count,
                           entered_by=self.profile_id)
        self._load_ratios(client)

    # ── publish ──
    @rx.event
    def publish(self):
        if not self.version_id:
            return
        client = self._client()
        publish_version(client, facility_id=self.facility_id,
                        roster_version_id=self.version_id, created_by=self.profile_id)
        self.status = RosterStatus.PUBLISHED
