"""Domain enums, statuses and display lookups mirroring the DB. Shift codes are intentionally NOT an enum - they're facility-configured data (`shift_definitions`)."""
from __future__ import annotations

from enum import StrEnum


class Rank(StrEnum):
    RN = "RN"
    EN = "EN"
    HW = "HW"
    HCA = "HCA"
    CW = "CW"
    PCW = "PCW"
    AW = "AW"
    PTA = "PTA"
    OTA = "OTA"
    SW = "SW"     # social worker
    PT = "PT"     # physiotherapist
    OT = "OT"     # occupational therapist


class EmploymentType(StrEnum):
    LOCAL_FT = "local_ft"
    LOCAL_PT = "local_pt"
    IMPORTED_LABOR = "imported_labor"
    AGENCY = "agency"
    OUTSOURCE = "outsource"
    CASUAL = "casual"


class Role(StrEnum):
    SUPERINTENDENT = "superintendent"
    ADMIN = "admin"
    STAFF = "staff"
    SCHEDULER = "scheduler"   # Phase 1.1 RBAC - builds/edits rosters
    HR = "hr"                 # Phase 1.1 RBAC - staff records
    AUDITOR = "auditor"       # Phase 1.1 RBAC - read-only compliance review


class RosterStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PublishEvent(StrEnum):
    SAVE_DRAFT = "save_draft"
    PUBLISH = "publish"
    ROLLBACK = "rollback"


class OverrideAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


# ── solver / optimization (Phase 2) ─────────────────────────────────────────
class PlanMode(StrEnum):
    """Roster option. Values match roster_versions.version_type."""
    A = "A"   # Cost-Optimized
    B = "B"   # Staff-Satisfaction
    C = "C"   # Balanced


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SolveStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class ViolationCode(StrEnum):
    COVERAGE = "coverage"
    RATIO = "ratio"
    REST = "rest"
    OVERLAP = "overlap"
    MAX_HOURS = "max_hours"
    LEAVE = "leave"
    ELIGIBILITY = "eligibility"


# Below this score a roster has unresolved hard violations and isn't publishable.
PUBLISH_THRESHOLD = 60


# ── rank substitution (Phase 3: emergency cover eligibility) ────────────────
# Care ranks form a seniority ladder: a more senior care rank may cover a less
# senior slot, never the other way round. Therapy/social ranks are not
# interchangeable with care ranks at all - only an exact match covers them.
CARE_RANKS = frozenset({"RN", "EN", "HW", "HCA", "CW", "PCW", "AW"})
RANK_SENIORITY: dict[str, int] = {
    "RN": 7, "EN": 6, "HW": 5, "HCA": 4, "CW": 4, "PCW": 3, "AW": 2,
}


def can_cover_rank(candidate_rank: str | None, required_rank: str | None) -> bool:
    """May `candidate_rank` be rostered into a slot that asks for `required_rank`?"""
    if not required_rank or candidate_rank == required_rank:
        return True
    if candidate_rank not in CARE_RANKS or required_rank not in CARE_RANKS:
        return False
    return RANK_SENIORITY.get(candidate_rank, 0) >= RANK_SENIORITY.get(required_rank, 0)


# ── Emma AI commercial tiers (NAAC pricing, HK$/user/month) ─────────────────
# Pricing is a product decision, not facility data, so it lives in code; the
# per-facility ROI baseline that multiplies against it lives in roi_settings.
EMMA_TIERS: tuple[dict, ...] = (
    {"tier": 1, "label": "300–500",     "max_staff": 500,  "rates": {"3yr": 48, "5yr": 45, "10yr": 42}},
    {"tier": 2, "label": "501–800",     "max_staff": 800,  "rates": {"3yr": 45, "5yr": 42, "10yr": 39}},
    {"tier": 3, "label": "801–1,200",   "max_staff": 1200, "rates": {"3yr": 42, "5yr": 39, "10yr": 36}},
    {"tier": 4, "label": "1,201–1,700", "max_staff": 1700, "rates": {"3yr": 39, "5yr": 36, "10yr": 33}},
)


def tier_for(total_staff: int) -> dict:
    for t in EMMA_TIERS:
        if total_staff <= t["max_staff"]:
            return t
    return EMMA_TIERS[-1]


# ── shift-cell display styling (background, foreground) ─────────────────────
SHIFT_STYLE: dict[str, tuple[str, str]] = {
    "A": ("#DBEAFE", "#1E40AF"), "B": ("#CFFAFE", "#155E75"),
    "E": ("#CCFBF1", "#115E59"), "P": ("#FEF3C7", "#92400E"),
    "N": ("#E0E7FF", "#3730A3"), "AN": ("#EDE9FE", "#5B21B6"),
    "7A": ("#DBEAFE", "#1E40AF"), "9A": ("#CFFAFE", "#155E75"),
    "7P": ("#E0E7FF", "#3730A3"),
    "AL": ("#DCFCE7", "#166534"), "SLEEP": ("#F5F3FF", "#6D28D9"),
    "OFF": ("#F1F5F9", "#64748B"), "DO": ("#F1F5F9", "#64748B"),
}
DEFAULT_STYLE: tuple[str, str] = ("#F1F5F9", "#475569")
