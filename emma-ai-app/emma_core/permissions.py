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
    # The seven KPI screens were not in the v1 document and were provisionally
    # treated as reports. Cherry's v2 gives them their own matrix, and splits one
    # of them out: staffing-ratio compliance is narrower than the rest, not wider.
    KPI = "kpi"
    KPI_STAFFING_RATIO = "kpi.staffing_ratio"
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
    # ALLIED_HEALTH holds R on leave and duty, scoped to its own discipline -
    # a physiotherapist may recommend on a physiotherapist's request and on
    # nobody else's. The grant says R; `recommend_scope()` says how far it
    # reaches, and `DOMAIN_SCOPED_RECOMMEND` below is the list.
    #
    # APPROVE_SICK stays X. Cherry confirmed "leave/duty approvals" and named
    # those two; sick leave was not in the answer, and the house rule is that an
    # unstated cell denies. One word from her widens it.
    Feature.APPROVE_LEAVE:        (F,     R,     R,      R,     S),
    Feature.APPROVE_DUTY_DO:      (F,     R,     R,      R,     S),
    Feature.APPROVE_SICK:         (F,     R,     X,      R,     S),
    Feature.OT_REVIEW:            (F,     R,     X,      V,     S),
    Feature.TOIL:                 (F,     R,     X,      V,     S),
    Feature.STAFF_PORTFOLIO:      (F,     V,     V,      E,     S),
    Feature.CERTIFICATES:         (F,     V,     V,      E,     S),
    Feature.STAFF_PROFILE_WRITE:  (F,     X,     X,      E,     X),  # clerk drafts, OWNER activates
    Feature.WORKING_HOURS:        (F,     E,     X,      E,     X),
    Feature.REPORTS:              (F,     V,     X,      V,     X),
    Feature.COMPLIANCE:           (F,     V,     V,      V,     X),
    Feature.KPI:                  (F,     V,     X,      V,     X),
    # Narrower than both KPI and COMPLIANCE, and deliberately so. The v1 guess
    # put this under COMPLIANCE, reasoning that a therapist has cause to know
    # whether the floor is legally staffed. Cherry's v2 says no: ALLIED_HEALTH
    # and ADMIN_CLERK are both out. Overruled and corrected.
    Feature.KPI_STAFFING_RATIO:   (F,     V,     X,      X,     X),
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

# CONFIRMED by Cherry, 1 Aug 2026: "Your assumptions are 100% correct."
#
# The v1 document defined SCHEDULER and HR_AUDITOR in the role table but shipped
# no matrix columns for them, so these two rows were derived from their one-line
# definitions and flagged provisional. Both are now confirmed as written, plus
# two explicit answers to the questions raised with them:
#
#   SCHEDULER   "authorised roster drafter; cannot publish". Drafts and edits a
#               roster, corrects hours, never publishes. **Does not recommend on
#               leave** - confirmed; "they just draft".
#   HR_AUDITOR  "read-only + cert management". Reads what a manager reads plus the
#               audit log, edits certificates only, approves nothing. **Does not
#               see ROI** - confirmed.
#
# Both err towards less access, which was the principle Cherry endorsed:
# widening a role later is a config change, discovering it was too wide is an
# incident.
_EXTRA_COLUMNS: dict[SystemRole, dict[Feature, Grant]] = {
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
        Feature.KPI: V,
        Feature.KPI_STAFFING_RATIO: V,
        Feature.COVER_VIEW_ANALYSIS: V,
        Feature.STAFF_PORTFOLIO: V,
        # No APPROVE_* row: a scheduler drafts and does not review. Confirmed.
    },
    SystemRole.HR_AUDITOR: {
        Feature.DASHBOARD: V,
        Feature.ROSTER_VIEW: V,
        Feature.STAFF_PORTFOLIO: V,
        Feature.CERTIFICATES: E,
        Feature.WORKING_HOURS: V,
        Feature.REPORTS: V,
        Feature.KPI: V,
        Feature.KPI_STAFFING_RATIO: V,
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
        # No ROI row: confirmed out.
    },
}

# ── domain-scoped recommendation ─────────────────────────────────────────────
# "R for leave/duty approvals within their own domain only (e.g. PT approving PT
# leave)" - Cherry, 1 Aug 2026.
#
# This is the first grant in the matrix that is not answerable from the role
# alone. Every other cell is a yes or a no; this one is "yes, about these
# people". So the grant stays R and the reach is a separate question, asked
# through `recommend_scope()`. Encoding it as a new Grant value instead would
# have meant every existing `grant is Grant.RECOMMEND` check silently stopped
# matching a therapist - failing open or closed depending on the call site,
# which is the worst property a permission change can have.
#
# Domain is the therapist's own discipline, not all of allied health. Cherry's
# example is a PT approving PT leave; an OT is a different profession and a PT
# has no standing to review their caseload cover.
DOMAIN_SCOPED_RECOMMEND: frozenset[tuple[SystemRole, Feature]] = frozenset({
    (SystemRole.ALLIED_HEALTH, Feature.APPROVE_LEAVE),
    (SystemRole.ALLIED_HEALTH, Feature.APPROVE_DUTY_DO),
})

# Which ranks each discipline covers. An assistant belongs to the discipline
# they assist, so a physiotherapist may recommend on their PTA's leave - that is
# the person whose absence they have to cover.
THERAPY_DOMAINS: dict[str, frozenset[str]] = {
    "PT":  frozenset({"PT", "PTA"}),
    "PTA": frozenset({"PT", "PTA"}),
    "OT":  frozenset({"OT", "OTA"}),
    "OTA": frozenset({"OT", "OTA"}),
    "ST":  frozenset({"ST", "STA"}),
    "STA": frozenset({"ST", "STA"}),
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
    extra = _EXTRA_COLUMNS.get(resolved)
    if extra is not None:
        return extra.get(feature, Grant.NONE)
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
    """Whether the role may recommend at all.

    Deliberately does not consider domain. A therapist *can* recommend on leave,
    which is what decides whether they see the review UI and whether the endpoint
    exists for them; *whose* leave is `may_recommend_for()`. Merging the two would
    make a therapist with no PT colleagues look like a role without the grant.
    """
    return grant_for(role, feature) in RECOMMEND_GRANTS


def recommend_scope(role: str | SystemRole | None,
                    feature: Feature) -> str | None:
    """`'facility'`, `'own_domain'`, or None when the role cannot recommend."""
    if not can_recommend(role, feature):
        return None
    resolved = normalise_role(role)
    if (resolved, feature) in DOMAIN_SCOPED_RECOMMEND:
        return "own_domain"
    return "facility"


def domain_ranks(rank: str | None) -> frozenset[str] | None:
    """The ranks a domain-scoped recommender covers, or None if unmapped.

    None means "this rank has no defined domain", and callers must treat that as
    covering nobody. Returning the empty set would read the same at the call site
    but hide the difference between a therapist with no assistants and a rank we
    have simply never mapped.
    """
    return THERAPY_DOMAINS.get(str(rank or "").upper())


def may_recommend_for(role: str | SystemRole | None, feature: Feature, *,
                      recommender_rank: str | None,
                      subject_rank: str | None) -> bool:
    """May this person recommend on *this* request?

    Facility-scoped roles ignore both ranks. A domain-scoped one has to match:
    an unmapped rank on either side is a no, because the safe reading of "I do
    not know whether these two are the same discipline" is that they are not.
    """
    scope = recommend_scope(role, feature)
    if scope is None:
        return False
    if scope == "facility":
        return True
    covered = domain_ranks(recommender_rank)
    if not covered or not subject_rank:
        return False
    return str(subject_rank).upper() in covered


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
