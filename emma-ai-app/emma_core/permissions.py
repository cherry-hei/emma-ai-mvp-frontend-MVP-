"""Role x feature permission matrix (spec 1.1).

Transcribed from "Emma AI - RBAC Definition for Implementation
(Salvation Army x NAAC)", 30 Jul 2026, authored by Cherry. That document is the
source of truth; this module is its executable form. When the document changes,
change the tables here - not the call sites.

Two ideas from the document drive the whole design:

*One role set, many job titles.*
    Each NGO's real job titles map onto the same seven system roles, so a third
    NGO is a new mapping row and no new code. Job-title -> role mapping is
    facility data (see `facility_config`); this module only knows the roles.

*Recommend is not approve.*
    A nursing officer, a therapist and an admin clerk may all attach a
    "suggest approve / suggest reject" with a reason to a pending request. None
    of them may decide it. Final approval belongs to OWNER alone - the
    superintendent/deputy at Salvation Army, the 主任/副主任 at NAAC. `RECOMMEND`
    exists as a distinct grant rather than a flavour of write so that the
    approve endpoint can return 403 to exactly the people whose job it is to
    review it first.

`grant_for()` is the only lookup call sites should need. Anything absent from
the matrix denies, so a feature added without a matrix row is closed to
everyone but OWNER rather than silently open - the failure mode that let a
FRONTLINE token read /roi/summary.
"""
from __future__ import annotations

from enum import StrEnum


class SystemRole(StrEnum):
    """The seven roles. Values are the canonical wire/DB form."""

    OWNER = "OWNER"                   # top 1-2 of facility; final approval
    NURSE_MGR = "NURSE_MGR"           # nursing officer; recommend + draft nursing roster
    ALLIED_HEALTH = "ALLIED_HEALTH"   # PT/OT/ST; recommend within own domain
    ADMIN_CLERK = "ADMIN_CLERK"       # clerical/admin (incl. NAAC social workers for MVP)
    SCHEDULER = "SCHEDULER"           # authorised roster drafter; cannot publish
    FRONTLINE = "FRONTLINE"           # Staff App users; self-only
    HR_AUDITOR = "HR_AUDITOR"         # HQ HR/audit; read-only + cert management


class Grant(StrEnum):
    """Permission codes. Values match the legend in the RBAC document."""

    FULL = "F"          # view + edit + final approve/reject/cancel/revoke
    RECOMMEND = "R"     # view + suggest approve/reject + comment; CANNOT decide
    EDIT = "E"          # view + edit data, no approval rights
    VIEW = "V"          # read-only; write APIs 403
    SELF = "S"          # own records only; API filtered by user_id
    NONE = "-"          # hide menu + route guard redirect + API 403


# Legacy role values still present in the database and in seeded accounts. The
# rename to the canonical seven is a separate migration; until it lands, both
# spellings resolve through `normalise_role()` so no account is locked out.
#
# `hr` and `auditor` both collapse into HR_AUDITOR because the document defines
# one combined role. That merge widens `auditor` slightly (it gains certificate
# editing) and narrows `hr` (it loses nothing it was actually granted).
LEGACY_ROLE_ALIASES: dict[str, SystemRole] = {
    "superintendent": SystemRole.OWNER,
    "admin": SystemRole.ADMIN_CLERK,
    "staff": SystemRole.FRONTLINE,
    "scheduler": SystemRole.SCHEDULER,
    "hr": SystemRole.HR_AUDITOR,
    "auditor": SystemRole.HR_AUDITOR,
}


class Feature(StrEnum):
    """One entry per row of the document's feature tables."""

    # -- shared: both NGOs (document section 1 table) ------------------------
    DASHBOARD = "dashboard"
    ROSTER_VIEW = "roster.view"
    ROSTER_AI_DRAFT = "roster.ai_draft"
    ROSTER_PUBLISH = "roster.publish"
    COVER_VIEW_ANALYSIS = "cover.view_analysis"
    COVER_ASSIGN = "cover.assign"
    APPROVE_LEAVE = "approve.leave"
    APPROVE_DUTY_DO = "approve.duty_do"
    APPROVE_SICK = "approve.sick"
    OT_REVIEW = "ot.review"
    TOIL = "toil"
    STAFF_PORTFOLIO = "staff.portfolio"
    CERTIFICATES = "staff.certificates"
    STAFF_PROFILE_WRITE = "staff.profile_write"
    WORKING_HOURS = "working_hours"
    REPORTS = "reports"
    COMPLIANCE = "compliance"
    ALERTS = "alerts"
    ROI = "roi"
    FACILITY_SETTINGS = "facility.settings"
    FORM_BUILDER = "facility.form_builder"
    AUDIT_LOG = "audit_log"

    # -- NAAC-specific (document section 2 table) ---------------------------
    ROSTER_RULE_ENGINE = "roster.rule_engine"
    DUTY_MANAGER_ALLOC = "duty_manager.alloc"
    MEDICAL_ESCORT = "medical_escort"
    TASK_CODES = "task_codes"
    DUAL_HOURS_REGIME = "hours.dual_regime"


F, R, E, V, S, X = (
    Grant.FULL, Grant.RECOMMEND, Grant.EDIT, Grant.VIEW, Grant.SELF, Grant.NONE,
)

# The matrix, verbatim from the document. Column order below is fixed by
# `_COLUMNS`; a row is a tuple in that order, which keeps this readable as the
# table it came from rather than as nested dicts.
_COLUMNS: tuple[SystemRole, ...] = (
    SystemRole.OWNER,
    SystemRole.NURSE_MGR,
    SystemRole.ALLIED_HEALTH,
    SystemRole.ADMIN_CLERK,
    SystemRole.FRONTLINE,
)

_MATRIX: dict[Feature, tuple[Grant, ...]] = {
    #                              OWNER  NURSE  ALLIED  CLERK  FRONT
    Feature.DASHBOARD:            (F,     V,     V,      V,     X),
    Feature.ROSTER_VIEW:          (F,     V,     V,      V,     S),  # app: own
    Feature.ROSTER_AI_DRAFT:      (F,     E,     X,      X,     X),
    Feature.ROSTER_PUBLISH:       (F,     X,     X,      X,     X),
    Feature.COVER_VIEW_ANALYSIS:  (F,     V,     X,      V,     X),
    Feature.COVER_ASSIGN:         (F,     R,     X,      X,     X),
    Feature.APPROVE_LEAVE:        (F,     R,     X,      R,     S),
    Feature.APPROVE_DUTY_DO:      (F,     R,     X,      R,     S),
    Feature.APPROVE_SICK:         (F,     R,     X,      R,     S),
    Feature.OT_REVIEW:            (F,     R,     X,      V,     S),
    Feature.TOIL:                 (F,     R,     X,      V,     S),
    Feature.STAFF_PORTFOLIO:      (F,     V,     V,      E,     S),
    Feature.CERTIFICATES:         (F,     V,     V,      E,     S),
    Feature.STAFF_PROFILE_WRITE:  (F,     X,     X,      E,     X),  # clerk drafts, OWNER activates
    Feature.WORKING_HOURS:        (F,     E,     X,      E,     X),
    Feature.REPORTS:              (F,     V,     X,      V,     X),
    Feature.COMPLIANCE:           (F,     V,     V,      V,     X),
    Feature.ALERTS:               (F,     V,     X,      V,     S),  # app: own notifications
    Feature.ROI:                  (F,     X,     X,      X,     X),
    Feature.FACILITY_SETTINGS:    (F,     X,     X,      X,     X),
    Feature.FORM_BUILDER:         (F,     X,     X,      E,     X),
    Feature.AUDIT_LOG:            (F,     X,     X,      X,     X),
    # NAAC-specific rows. The document states the shared rows "apply
    # identically", so these extend rather than replace the table above.
    Feature.ROSTER_RULE_ENGINE:   (F,     V,     X,      V,     X),
    Feature.DUTY_MANAGER_ALLOC:   (F,     R,     X,      V,     X),
    Feature.MEDICAL_ESCORT:       (F,     E,     V,      E,     S),
    Feature.TASK_CODES:           (F,     E,     E,      V,     S),
    Feature.DUAL_HOURS_REGIME:    (F,     E,     X,      E,     X),
}

# PROVISIONAL - awaiting Cherry's confirmation.
#
# The document defines SCHEDULER and HR_AUDITOR in the role table but ships no
# matrix columns for them, so these two rows are derived from their one-line
# definitions and are the only entries here not traceable to the source:
#
#   SCHEDULER   "authorised roster drafter; cannot publish" -> may draft and edit
#               a roster and correct hours, never publishes, holds no approval or
#               recommendation rights, and cannot see ROI, audit log or settings.
#   HR_AUDITOR  "read-only + cert management" -> reads everything a manager reads
#               plus the audit log, edits certificates only, approves nothing.
#
# Both deliberately err towards less access: widening a role later is a config
# change, discovering it was too wide is an incident.
_PROVISIONAL: dict[SystemRole, dict[Feature, Grant]] = {
    SystemRole.SCHEDULER: {
        Feature.DASHBOARD: V,
        Feature.ROSTER_VIEW: V,
        Feature.ROSTER_AI_DRAFT: E,
        Feature.ROSTER_PUBLISH: X,
        Feature.ROSTER_RULE_ENGINE: V,
        Feature.WORKING_HOURS: E,
        Feature.TASK_CODES: V,
        Feature.MEDICAL_ESCORT: V,
        Feature.DUTY_MANAGER_ALLOC: V,
        Feature.DUAL_HOURS_REGIME: V,
        Feature.COMPLIANCE: V,
        Feature.REPORTS: V,
        Feature.COVER_VIEW_ANALYSIS: V,
        Feature.STAFF_PORTFOLIO: V,
    },
    SystemRole.HR_AUDITOR: {
        Feature.DASHBOARD: V,
        Feature.ROSTER_VIEW: V,
        Feature.STAFF_PORTFOLIO: V,
        Feature.CERTIFICATES: E,
        Feature.WORKING_HOURS: V,
        Feature.REPORTS: V,
        Feature.COMPLIANCE: V,
        Feature.ALERTS: V,
        Feature.AUDIT_LOG: V,
        Feature.OT_REVIEW: V,
        Feature.TOIL: V,
        Feature.TASK_CODES: V,
        Feature.MEDICAL_ESCORT: V,
        Feature.DUAL_HOURS_REGIME: V,
        Feature.ROSTER_RULE_ENGINE: V,
        Feature.DUTY_MANAGER_ALLOC: V,
        Feature.COVER_VIEW_ANALYSIS: V,
    },
}

# Grants that let a request read the facility-wide view of a feature.
READ_GRANTS: frozenset[Grant] = frozenset({Grant.FULL, Grant.RECOMMEND,
                                           Grant.EDIT, Grant.VIEW})
# Grants that let a request change facility-wide data.
WRITE_GRANTS: frozenset[Grant] = frozenset({Grant.FULL, Grant.EDIT})
# Grants that let a request attach a recommendation to a pending decision.
RECOMMEND_GRANTS: frozenset[Grant] = frozenset({Grant.FULL, Grant.RECOMMEND})
# Only F decides. This is the "recommend != approve" rule in one line.
DECIDE_GRANTS: frozenset[Grant] = frozenset({Grant.FULL})


def normalise_role(role: str | SystemRole | None) -> SystemRole | None:
    """Accept a canonical role, a legacy DB value or None."""
    if role is None:
        return None
    if isinstance(role, SystemRole):
        return role
    raw = str(role).strip()
    if not raw:
        return None
    try:
        return SystemRole(raw.upper())
    except ValueError:
        return LEGACY_ROLE_ALIASES.get(raw.lower())


def grant_for(role: str | SystemRole | None, feature: Feature) -> Grant:
    """The grant `role` holds over `feature`. Unknown role or missing row denies."""
    resolved = normalise_role(role)
    if resolved is None:
        return Grant.NONE
    provisional = _PROVISIONAL.get(resolved)
    if provisional is not None:
        return provisional.get(feature, Grant.NONE)
    row = _MATRIX.get(feature)
    if row is None:
        return Grant.NONE
    try:
        return row[_COLUMNS.index(resolved)]
    except ValueError:
        return Grant.NONE


def can_read(role: str | SystemRole | None, feature: Feature) -> bool:
    """Facility-wide read. `S` is deliberately excluded - self-only is not a
    facility read, and conflating the two is how a staff token reads the home's
    financials."""
    return grant_for(role, feature) in READ_GRANTS


def can_write(role: str | SystemRole | None, feature: Feature) -> bool:
    return grant_for(role, feature) in WRITE_GRANTS


def can_recommend(role: str | SystemRole | None, feature: Feature) -> bool:
    return grant_for(role, feature) in RECOMMEND_GRANTS


def can_decide(role: str | SystemRole | None, feature: Feature) -> bool:
    """Final approve/reject/cancel/revoke. OWNER only, by design."""
    return grant_for(role, feature) in DECIDE_GRANTS


def is_self_only(role: str | SystemRole | None, feature: Feature) -> bool:
    """True when the caller may see the feature but only their own rows, so the
    service filters by user instead of returning 403."""
    return grant_for(role, feature) is Grant.SELF


def visible_features(role: str | SystemRole | None) -> frozenset[Feature]:
    """Every feature the role may reach at all, self-only included. Drives the
    frontend menu so the sidebar and the API agree on what exists."""
    return frozenset(
        f for f in Feature if grant_for(role, f) is not Grant.NONE
    )
