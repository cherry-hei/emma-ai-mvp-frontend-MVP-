"""NAAC's implemented HTTP surface; anything outside it is closed by default.

Route-specific dependencies still enforce the action and record scope. This
outer gate prevents an older get_ctx-only route from widening NAAC permissions
while the remaining legacy API surfaces are reviewed. It never grants access.
"""
from __future__ import annotations

from emma_core.permissions import Feature


def naac_route_enabled(ctx, path: str, method: str) -> bool:
    read = method in ("GET", "HEAD")
    access = ctx.profile.care_workflow
    facility_scope = access.roster_scope == "facility"

    # These payloads are identity-scoped, or dictionaries needed to interpret
    # one's own roster. Unit ids/organisation home lists are filtered by handlers.
    if path.startswith("/me/"):
        return bool(ctx.profile.staff_id)
    if read and path in (
        "/shift-definitions", "/task-definitions", "/escort-locations", "/calendar-days", "/units",
        "/organisations/current", "/organisations/current/facilities",
    ):
        return True
    if path == "/dashboard/summary" and read:
        return ctx.can_read(Feature.DASHBOARD)
    if path in ("/roster-periods", "/roster-versions", "/rosters/{period_id}"):
        return ctx.can_read(Feature.ROSTER_VIEW) if read else ctx.allows("roster_generate")
    if path == "/shifts":
        return ctx.allows("roster_delete" if method == "DELETE" else "roster_edit")
    if path == "/rosters/{version_id}/save-draft":
        return ctx.allows("roster_edit")
    if path == "/rosters/{version_id}/publish":
        return ctx.allows("roster_publish")
    if (path.startswith("/optimize") or path.startswith("/optimization-jobs")
            or path.startswith("/roster-option-scores")):
        return ctx.allows("roster_generate")
    if path == "/validate-roster" or path.startswith("/imports"):
        return ctx.allows("roster_batch")
    if path.startswith("/leave-requests"):
        # Handlers separate self, recommendations and final decisions.
        return ctx.can_read(Feature.APPROVE_LEAVE) or ctx.is_self_only(Feature.APPROVE_LEAVE)
    if path.startswith("/swap-requests"):
        return bool(ctx.profile.staff_id) or ctx.can_read(Feature.APPROVE_DUTY_DO)
    if path == "/roster-cell-locks":
        return facility_scope and ctx.can_read(Feature.ROSTER_VIEW)
    if path == "/staff":
        return (ctx.can_read(Feature.STAFF_PORTFOLIO) or ctx.allows("roster_edit")) if read else ctx.allows("staff_manage")
    if path.startswith("/staff/"):
        return ctx.can_read(Feature.STAFF_PORTFOLIO) if read else ctx.allows("staff_manage")
    if path.startswith("/reports") or path.startswith("/exports/"):
        return ctx.can_read(Feature.REPORTS)
    if path.startswith("/audit-logs"):
        return ctx.can_read(Feature.AUDIT_LOG)
    if path.startswith("/facility-configs") or path == "/shift-definitions":
        return ctx.can_read(Feature.FACILITY_SETTINGS) if read else ctx.allows("rules_manage")
    if path == "/calendar-days" or path.startswith("/compliance/rule-definitions"):
        return ctx.can_read(Feature.ROSTER_RULE_ENGINE) if read else ctx.allows("rules_manage")
    if path.startswith(("/floor-rules", "/staff-qualifications")):
        return facility_scope and (ctx.can_read(Feature.TASK_CODES) if read else ctx.allows("rules_manage"))
    if path in ("/task-assignments", "/task-assignments/{task_assignment_id}"):
        # Nurse cell-editor hydration/timing writes are scoped by the handler
        # through the exact shift assignment, unit and manual-draft version.
        if not facility_scope:
            return ctx.allows("roster_edit") and method in ("GET", "POST", "PATCH")
        return ctx.can_read(Feature.TASK_CODES) if read else ctx.can_write(Feature.TASK_CODES)
    if path.startswith(("/task-assignments", "/facility-events", "/escort-locations", "/escorts")):
        return facility_scope and (ctx.can_read(Feature.TASK_CODES) if read else ctx.can_write(Feature.TASK_CODES))
    return False
