"""Reflex state for the Emma AI manager dashboard.

Event handlers run server-side in Python, so they call emma_core services
directly. State holds display-ready view-models (formatting done here, not in
templates) to keep the component tree free of Var string-ops.
"""
from __future__ import annotations

import dataclasses

import reflex as rx

from emma_core.config import settings
from emma_core.constants import (
    DEFAULT_STYLE, PUBLISH_THRESHOLD, SHIFT_STYLE, PlanMode, RosterStatus,
)
from emma_core.db import get_user_client
from emma_core.models import OptimizeRequest
from emma_core.services import optimize as optimize_svc
from emma_core.services.auth import get_profile, sign_in
from emma_core.services.compliance import compute_ratios
from emma_core.services.residents import get_units, set_resident_count
from emma_core.services.roster import (
    clear_cell, get_roster_grid, get_shift_defs, publish_version, set_cell,
)

DEV_PASSWORD = "EmmaDev123!"

# Display metadata for each solver plan (title, what it optimizes for, recommended?).
PLAN_META: dict[str, tuple[str, str, bool]] = {
    PlanMode.A: ("Cost-Optimized", "Minimize agency & overtime", False),
    PlanMode.B: ("Staff-Satisfaction", "Honor requests & days off", False),
    PlanMode.C: ("Balanced", "Recommended middle ground", True),
}


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


@dataclasses.dataclass
class OptionVM:
    """Display-ready solver option (one A/B/C roster) for the comparison panel."""
    plan_mode: str = ""
    title: str = ""
    optimizes_for: str = ""
    recommended: bool = False
    score: int = 0
    publishable: bool = False          # score >= PUBLISH_THRESHOLD and has no hard gaps
    hard_violations: int = 0
    status: str = ""                   # solver status (optimal/feasible/infeasible)
    published: bool = False
    version_id: str = ""
    reason: str = ""                   # infeasible reasons, joined (empty if clean)
    kpi_agency: str = ""
    kpi_ot: str = ""
    kpi_coverage_gap: str = ""
    kpi_deviation: str = ""
    kpi_fairness: str = ""


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
    version_id: str = ""            # the manual roster version (source of truth)
    period_id: str = ""
    status: str = ""
    period_label: str = ""
    ratio_date: str = ""
    dates: list[str] = []
    rows: list[RowVM] = []
    ratios: list[RatioVM] = []
    shift_types: list[str] = []
    unit_names: list[str] = []

    # ── AI roster options (Phase 2 solver) ──
    options: list[OptionVM] = []
    generating: bool = False
    optimize_error: str = ""
    viewing_version_id: str = ""   # "" = showing the manual roster; else an A/B/C option
    viewing_label: str = ""

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

    @rx.var
    def has_options(self) -> bool:
        return len(self.options) > 0

    @rx.var
    def previewing(self) -> bool:
        return bool(self.viewing_version_id)

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

        # always open on the manual roster; drop any prior preview / options
        self.viewing_version_id = ""
        self.viewing_label = ""
        self.options = []
        self.optimize_error = ""

        grid = get_roster_grid(client, self.facility_id)
        self.version_id = grid.version_id or ""
        self.period_id = grid.period_id or ""
        if grid.period_start and grid.period_end:
            self.period_label = f"{grid.period_start:%d %b} – {grid.period_end:%d %b %Y}"
        self.ratio_date = grid.dates[0].isoformat() if grid.dates else ""
        self._apply_grid(grid)
        self._load_ratios(client, self.version_id)

    def _apply_grid(self, grid) -> None:
        self.status = grid.status or ""
        self.dates = [d.strftime("%a %d/%m") for d in grid.dates]
        self.rows = rows_from_grid(grid)

    def _refresh(self, client) -> None:
        """Reload the manual roster (manual edits never touch an auto option)."""
        grid = get_roster_grid(client, self.facility_id)
        self.version_id = grid.version_id or self.version_id
        self._apply_grid(grid)
        self._load_ratios(client, self.version_id)

    def _load_ratios(self, client, version_id: str) -> None:
        if not self.ratio_date or not version_id:
            self.ratios = []
            return
        self.ratios = [
            RatioVM(label=x.label, count_label=f"{x.actual}/{x.required}",
                    verdict="OK" if x.passes else "SHORT", ok=x.passes)
            for x in compute_ratios(client, self.facility_id, self.ratio_date,
                                    roster_version_id=version_id)
        ]

    # ── shift editor ──
    @rx.event
    def open_editor(self, staff_id: str, staff_name: str, date: str, label: str, tasks: list[str]):
        if self.viewing_version_id:
            return  # previewing an auto option is read-only; edits apply to the manual roster
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
        self._load_ratios(client, self.viewing_version_id or self.version_id)

    # ── publish (manual roster) ──
    @rx.event
    def publish(self):
        if not self.version_id:
            return
        client = self._client()
        publish_version(client, facility_id=self.facility_id,
                        roster_version_id=self.version_id, created_by=self.profile_id)
        self.status = RosterStatus.PUBLISHED

    # ── AI roster options (Phase 2 solver) ──────────────────────────────────
    @rx.event
    def generate_options(self):
        """Run the CP-SAT solver for plans A/B/C and show them for comparison."""
        if not self.token or not self.period_id:
            self.optimize_error = "No roster period available to optimize."
            return
        self.optimize_error = ""
        self.generating = True
        yield  # flush state so the button shows its loading spinner
        client = self._client()
        try:
            resp = optimize_svc.run_optimization(
                client,
                OptimizeRequest(
                    facility_id=self.facility_id, period_id=self.period_id,
                    source_version_id=self.version_id or None,
                    created_by=self.profile_id,
                ),
            )
            self.options = [self._option_vm(o) for o in resp.roster_options]
        except Exception as exc:  # noqa: BLE001
            print("optimize error:", exc)
            self.optimize_error = "Optimization failed — please try again."
        finally:
            self.generating = False

    def _option_vm(self, o) -> OptionVM:
        pm = str(o.plan_mode)
        title, optimizes_for, recommended = PLAN_META.get(pm, (pm, "", False))
        k = o.kpi
        publishable = (bool(o.roster_version_id)
                       and o.constraint_score >= PUBLISH_THRESHOLD
                       and o.hard_violation_count == 0)
        return OptionVM(
            plan_mode=pm, title=title, optimizes_for=optimizes_for, recommended=recommended,
            score=o.constraint_score, publishable=publishable,
            hard_violations=o.hard_violation_count, status=str(o.status),
            version_id=o.roster_version_id or "",
            reason="; ".join(o.infeasible_reasons[:3]),
            kpi_agency=str(k.agency_count),
            kpi_ot=f"{k.ot_hours:g} h",
            kpi_coverage_gap=str(k.coverage_gap),
            kpi_deviation=str(k.deviation_from_baseline),
            kpi_fairness=f"{round(k.fairness_spread_minutes / 60, 1):g} h",
        )

    @rx.event
    def view_option(self, version_id: str, label: str):
        """Preview an A/B/C option in the roster grid (read-only)."""
        if not version_id:
            return
        client = self._client()
        grid = get_roster_grid(client, self.facility_id, version_type=None, version_id=version_id)
        self.viewing_version_id = version_id
        self.viewing_label = label
        self._apply_grid(grid)
        self._load_ratios(client, version_id)

    @rx.event
    def back_to_manual(self):
        client = self._client()
        self.viewing_version_id = ""
        self.viewing_label = ""
        grid = get_roster_grid(client, self.facility_id)
        self._apply_grid(grid)
        self._load_ratios(client, self.version_id)

    @rx.event
    def publish_option(self, version_id: str):
        """Publish a chosen A/B/C option (only allowed when it is publishable)."""
        if not version_id:
            return
        client = self._client()
        publish_version(client, facility_id=self.facility_id,
                        roster_version_id=version_id, created_by=self.profile_id)
        self.options = [
            dataclasses.replace(o, published=True) if o.version_id == version_id else o
            for o in self.options
        ]
        if self.viewing_version_id == version_id:
            self.status = RosterStatus.PUBLISHED
