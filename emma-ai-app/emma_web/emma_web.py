"""Emma AI manager dashboard (Reflex). Phase 1 slice: login, roster grid,
manual shift edit, resident-count input + staffing-ratio card, publish."""
import reflex as rx

from .state import AppState

BORDER = "1px solid #E2E8F0"


def top_bar() -> rx.Component:
    return rx.hstack(
        rx.hstack(rx.icon("calendar-check", size=22, color="#2563EB"),
                  rx.heading("Emma AI", size="5"), align="center", spacing="2"),
        rx.spacer(),
        rx.text(AppState.facility_name, weight="medium"),
        rx.badge(AppState.role, variant="soft", color_scheme="blue"),
        rx.button("Sign out", on_click=AppState.logout, variant="soft",
                  color_scheme="gray", size="2"),
        width="100%", align="center", padding="12px 20px",
        style={"borderBottom": BORDER},
    )


# ── roster grid ─────────────────────────────────────────────────────────────
def shift_cell(cell) -> rx.Component:
    return rx.table.cell(
        rx.box(
            rx.cond(
                cell.label != "",
                rx.box(cell.label, style={
                    "background": cell.bg, "color": cell.fg, "borderRadius": "6px",
                    "padding": "3px 0", "fontWeight": "600", "fontSize": "13px",
                    "textAlign": "center", "minWidth": "46px"}),
                rx.box("·", style={"color": "#CBD5E1", "textAlign": "center",
                                   "minWidth": "46px"}),
            ),
            on_click=AppState.open_editor(cell.staff_id, cell.staff_name,
                                          cell.date, cell.label, cell.tasks),
            style={"cursor": "pointer"},
        ),
        padding="4px",
    )


def roster_row(row) -> rx.Component:
    return rx.table.row(
        rx.table.row_header_cell(
            rx.vstack(
                rx.text(row.staff_name, weight="bold", size="2"),
                rx.text(row.subtitle, size="1", color="#64748B"),
                spacing="0", align="start"),
            style={"minWidth": "160px"}),
        rx.foreach(row.cells, shift_cell),
    )


def roster_table() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Staff"),
                    rx.foreach(AppState.dates,
                               lambda d: rx.table.column_header_cell(d)))),
            rx.table.body(rx.foreach(AppState.rows, roster_row)),
            variant="surface", size="1"),
        scrollbars="horizontal", type="auto", style={"width": "100%"},
    )


# ── ratio card + resident input ─────────────────────────────────────────────
def ratio_line(r) -> rx.Component:
    return rx.hstack(
        rx.text(r.label, size="2"),
        rx.spacer(),
        rx.text(r.count_label, size="2", weight="medium"),
        rx.cond(r.ok,
                rx.badge(r.verdict, color_scheme="green", variant="soft"),
                rx.badge(r.verdict, color_scheme="red", variant="soft")),
        width="100%", align="center",
    )


def ratio_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading("Staffing ratio (SWD)", size="4"),
                rx.spacer(),
                rx.badge(AppState.ratio_date, variant="soft", color_scheme="gray"),
                width="100%", align="center"),
            rx.hstack(
                rx.text("Residents:", size="2", color="#64748B"),
                rx.select(AppState.unit_names, value=AppState.resident_unit_name,
                          on_change=AppState.set_resident_unit_name),
                rx.input(value=AppState.resident_count_str,
                         on_change=AppState.set_resident_count_str,
                         type="number", width="90px"),
                rx.button("Update", on_click=AppState.save_resident_count, size="2"),
                spacing="2", align="center"),
            rx.divider(),
            rx.foreach(AppState.ratios, ratio_line),
            spacing="3", width="100%"),
        width="100%",
    )


# ── shift editor dialog ─────────────────────────────────────────────────────
def editor_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Edit shift"),
            rx.dialog.description(
                rx.hstack(rx.text(AppState.edit_staff_name, weight="bold"),
                          rx.text("·", color="#94A3B8"),
                          rx.text(AppState.edit_date), spacing="2")),
            rx.vstack(
                rx.text("Shift type", size="1", color="#64748B"),
                rx.select(AppState.shift_types, value=AppState.edit_shift_type,
                          on_change=AppState.set_edit_shift_type, width="100%"),
                rx.text("Tasks (comma separated)", size="1", color="#64748B"),
                rx.input(value=AppState.edit_tasks, on_change=AppState.set_edit_tasks,
                         placeholder="e.g. Med round, Vitals", width="100%"),
                rx.hstack(
                    rx.button("Clear shift", on_click=AppState.clear_current,
                              variant="soft", color_scheme="red"),
                    rx.spacer(),
                    rx.dialog.close(rx.button("Cancel", variant="soft", color_scheme="gray")),
                    rx.button("Save", on_click=AppState.save_cell),
                    width="100%", align="center"),
                spacing="2", width="100%", margin_top="8px"),
            style={"maxWidth": "420px"}),
        open=AppState.dialog_open, on_open_change=AppState.set_dialog,
    )


# ── AI roster options (Phase 2 solver) ───────────────────────────────────────
def _kpi_row(label: str, value) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="1", color="#64748B"),
        rx.spacer(),
        rx.text(value, size="1", weight="medium"),
        width="100%",
    )


def option_card(opt) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(f"Plan {opt.plan_mode}", color_scheme="blue", variant="solid"),
                rx.cond(
                    opt.recommended,
                    rx.badge("Recommended", color_scheme="grass", variant="soft"),
                    rx.fragment()),
                rx.spacer(),
                rx.cond(
                    opt.published,
                    rx.badge("Published", color_scheme="green"),
                    rx.fragment()),
                width="100%", align="center"),
            rx.heading(opt.title, size="4"),
            rx.text(opt.optimizes_for, size="1", color="#64748B"),
            rx.divider(),
            rx.hstack(
                rx.vstack(
                    rx.text("Score", size="1", color="#64748B"),
                    rx.cond(
                        opt.publishable,
                        rx.heading(opt.score, size="7", style={"color": "#16A34A"}),
                        rx.heading(opt.score, size="7", style={"color": "#DC2626"})),
                    spacing="0", align="start"),
                rx.spacer(),
                rx.vstack(
                    rx.text("Hard gaps", size="1", color="#64748B"),
                    rx.heading(opt.hard_violations, size="7"),
                    spacing="0", align="end"),
                width="100%", align="center"),
            rx.divider(),
            _kpi_row("Agency shifts", opt.kpi_agency),
            _kpi_row("Overtime", opt.kpi_ot),
            _kpi_row("Coverage gaps", opt.kpi_coverage_gap),
            _kpi_row("Δ from manual", opt.kpi_deviation),
            _kpi_row("Fairness spread", opt.kpi_fairness),
            rx.cond(
                opt.reason != "",
                rx.box(opt.reason, style={
                    "background": "#FEF3C7", "color": "#92400E", "borderRadius": "6px",
                    "padding": "6px 8px", "fontSize": "12px", "width": "100%"}),
                rx.fragment()),
            rx.hstack(
                rx.button("Preview", variant="soft", color_scheme="gray",
                          on_click=AppState.view_option(opt.version_id, opt.title),
                          disabled=opt.version_id == ""),
                rx.spacer(),
                rx.cond(
                    opt.publishable,
                    rx.button("Publish", on_click=AppState.publish_option(opt.version_id),
                              disabled=opt.published),
                    rx.tooltip(
                        rx.button("Publish", disabled=True, variant="soft"),
                        content="Unresolved coverage gaps — not safe to publish.")),
                width="100%", align="center"),
            spacing="2", width="100%", align="start"),
        width="100%",
    )


def optimizer_section() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("AI roster options", size="5"),
                rx.text("Generate three optimized rosters (Cost · Staff · Balanced) to compare.",
                        size="1", color="#64748B"),
                spacing="0", align="start"),
            rx.spacer(),
            rx.button(
                rx.icon("sparkles", size=16), "Generate A / B / C",
                on_click=AppState.generate_options, loading=AppState.generating, size="2"),
            width="100%", align="center"),
        rx.cond(
            AppState.optimize_error != "",
            rx.text(AppState.optimize_error, color="#DC2626", size="2"),
            rx.fragment()),
        rx.cond(
            AppState.has_options,
            rx.grid(rx.foreach(AppState.options, option_card),
                    columns=rx.breakpoints(initial="1", md="3"), spacing="3", width="100%"),
            rx.fragment()),
        spacing="3", width="100%",
    )


def preview_banner() -> rx.Component:
    return rx.cond(
        AppState.previewing,
        rx.hstack(
            rx.icon("eye", size=16, color="#2563EB"),
            rx.text("Previewing option ", size="2"),
            rx.text(AppState.viewing_label, size="2", weight="bold"),
            rx.text(" (draft) — this view is read-only.", size="2"),
            rx.spacer(),
            rx.button("Back to manual roster", size="1", variant="soft",
                      on_click=AppState.back_to_manual),
            width="100%", align="center", padding="8px 12px",
            style={"background": "#EFF6FF", "borderRadius": "8px",
                   "border": "1px solid #BFDBFE"}),
        rx.fragment(),
    )


# ── pages ───────────────────────────────────────────────────────────────────
def roster_page() -> rx.Component:
    return rx.vstack(
        top_bar(),
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Roster", size="6"),
                    rx.text(AppState.period_label, color="#64748B", size="2"),
                    spacing="0", align="start"),
                rx.spacer(),
                rx.cond(AppState.is_published,
                        rx.badge("Published", color_scheme="green", size="2"),
                        rx.badge("Draft", color_scheme="amber", variant="soft", size="2")),
                rx.button("Publish roster", on_click=AppState.publish,
                          disabled=AppState.is_published),
                width="100%", align="center"),
            rx.cond(
                AppState.previewing,
                rx.text("Preview is read-only. Return to the manual roster to edit.",
                        size="1", color="#94A3B8"),
                rx.text("Tip: click any cell to edit the shift.", size="1", color="#94A3B8")),
            preview_banner(),
            roster_table(),
            ratio_card(),
            rx.divider(),
            optimizer_section(),
            spacing="4", padding="20px", width="100%", style={"maxWidth": "1200px"}),
        editor_dialog(),
        width="100%", align="center", spacing="0",
    )


def login_page() -> rx.Component:
    return rx.center(
        rx.card(
            rx.vstack(
                rx.hstack(rx.icon("calendar-check", size=26, color="#2563EB"),
                          rx.heading("Emma AI", size="6"), align="center", spacing="2"),
                rx.text("Care-home rostering", color="#64748B", size="2"),
                rx.form(
                    rx.vstack(
                        rx.input(name="email", placeholder="Email", type="email",
                                 required=True, width="100%"),
                        rx.input(name="password", placeholder="Password",
                                 type="password", required=True, width="100%"),
                        rx.button("Sign in", type="submit", width="100%"),
                        spacing="3", width="100%"),
                    on_submit=AppState.login, width="100%"),
                rx.cond(
                    AppState.is_dev,
                    rx.vstack(
                        rx.divider(),
                        rx.text("Dev quick sign-in", size="1", color="#94A3B8"),
                        rx.hstack(
                            rx.button("Home A · Super",
                                      on_click=AppState.dev_login("super_a@emma.local"),
                                      variant="outline", size="1"),
                            rx.button("Home B · Super",
                                      on_click=AppState.dev_login("super_b@emma.local"),
                                      variant="outline", size="1"),
                            spacing="2"),
                        spacing="2", width="100%", align="center"),
                ),
                rx.cond(AppState.error != "",
                        rx.text(AppState.error, color="#DC2626", size="2")),
                spacing="4", width="100%", align="center"),
            style={"width": "360px", "padding": "28px"}),
        min_height="100vh",
    )


app = rx.App(theme=rx.theme(accent_color="blue", radius="large"))
app.add_page(login_page, route="/", title="Emma AI · Sign in")
app.add_page(roster_page, route="/roster", title="Emma AI · Roster",
             on_load=AppState.load_roster)
