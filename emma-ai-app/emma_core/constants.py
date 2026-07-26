"""Domain enums, statuses and display lookups mirroring the DB. Shift codes are intentionally NOT an enum — they're facility-configured data (`shift_definitions`)."""
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
    SCHEDULER = "scheduler"   # Phase 1.1 RBAC — builds/edits rosters
    HR = "hr"                 # Phase 1.1 RBAC — staff records
    AUDITOR = "auditor"       # Phase 1.1 RBAC — read-only compliance review


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
