"""RBAC matrix and guard tests (spec 1.1).

Acceptance criteria for 1.1 is "users see only permitted modules/data; RBAC tests
pass". The matrix assertions below are transcribed from Cherry's RBAC definition
of 30 Jul 2026 independently of `permissions.py` - if someone edits a row in the
module, a test here has to change too, which is the point.

The three regression tests at the end are the exact findings from her 2026-07-30
production testing: a staff token receiving 200 on /roi/summary, /reports and
/leave-requests.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps import (
    AuthCtx,
    get_ctx,
    require_decide,
    require_read,
    require_recommend,
    require_write,
)
from api.routers import leave as leave_router
from emma_core.models import Profile
from emma_core.permissions import (
    Feature,
    Grant,
    SystemRole,
    can_decide,
    can_read,
    can_recommend,
    can_write,
    grant_for,
    is_self_only,
    may_recommend_for,
    normalise_role,
    recommend_scope,
    visible_features,
)


def _ctx(role: str, *, staff_id: str | None = "staff-1") -> AuthCtx:
    return AuthCtx(
        token="test-token",
        client=object(),
        profile=Profile(id="profile-1", facility_id="f1", role=role, staff_id=staff_id),
    )


# ── the matrix, re-transcribed from the document ─────────────────────────────
# (feature, OWNER, NURSE_MGR, ALLIED_HEALTH, ADMIN_CLERK, FRONTLINE)
DOC_ROWS = [
    (Feature.DASHBOARD,           "F", "V", "V", "V", "-"),
    (Feature.ROSTER_VIEW,         "F", "V", "V", "V", "S"),
    (Feature.ROSTER_AI_DRAFT,     "F", "E", "-", "-", "-"),
    (Feature.ROSTER_PUBLISH,      "F", "-", "-", "-", "-"),
    (Feature.COVER_VIEW_ANALYSIS, "F", "V", "-", "V", "-"),
    (Feature.COVER_ASSIGN,        "F", "R", "-", "-", "-"),
    # ALLIED_HEALTH gained R on leave and duty in Cherry's 1 Aug answer,
    # scoped to its own discipline. APPROVE_SICK was not in that answer and
    # stays "-": an unstated cell denies.
    (Feature.APPROVE_LEAVE,       "F", "R", "R", "R", "S"),
    (Feature.APPROVE_DUTY_DO,     "F", "R", "R", "R", "S"),
    (Feature.APPROVE_SICK,        "F", "R", "-", "R", "S"),
    (Feature.OT_REVIEW,           "F", "R", "-", "V", "S"),
    (Feature.TOIL,                "F", "R", "-", "V", "S"),
    (Feature.STAFF_PORTFOLIO,     "F", "V", "V", "E", "S"),
    (Feature.CERTIFICATES,        "F", "V", "V", "E", "S"),
    (Feature.STAFF_PROFILE_WRITE, "F", "-", "-", "E", "-"),
    (Feature.WORKING_HOURS,       "F", "E", "-", "E", "-"),
    (Feature.REPORTS,             "F", "V", "-", "V", "-"),
    (Feature.COMPLIANCE,          "F", "V", "V", "V", "-"),
    (Feature.ALERTS,              "F", "V", "-", "V", "S"),
    (Feature.ROI,                 "F", "-", "-", "-", "-"),
    (Feature.FACILITY_SETTINGS,   "F", "-", "-", "-", "-"),
    (Feature.FORM_BUILDER,        "F", "-", "-", "E", "-"),
    (Feature.AUDIT_LOG,           "F", "-", "-", "-", "-"),
    # NAAC-specific rows
    (Feature.ROSTER_RULE_ENGINE,  "F", "V", "-", "V", "-"),
    (Feature.DUTY_MANAGER_ALLOC,  "F", "R", "-", "V", "-"),
    (Feature.MEDICAL_ESCORT,      "F", "E", "V", "E", "S"),
    (Feature.TASK_CODES,          "F", "E", "E", "V", "S"),
    (Feature.DUAL_HOURS_REGIME,   "F", "E", "-", "E", "-"),
]

DOC_COLUMNS = (
    SystemRole.OWNER,
    SystemRole.NURSE_MGR,
    SystemRole.ALLIED_HEALTH,
    SystemRole.ADMIN_CLERK,
    SystemRole.FRONTLINE,
)


@pytest.mark.parametrize("row", DOC_ROWS, ids=lambda r: r[0].value)
def test_matrix_matches_the_rbac_document(row):
    feature, *codes = row
    for role, code in zip(DOC_COLUMNS, codes, strict=True):
        assert grant_for(role, feature) == Grant(code), (
            f"{role.value} x {feature.value}: module says "
            f"{grant_for(role, feature).value!r}, document says {code!r}"
        )


def test_every_feature_has_a_row_for_every_role():
    """A feature added without matrix rows must deny, never default open."""
    for feature in Feature:
        for role in SystemRole:
            assert isinstance(grant_for(role, feature), Grant)


def test_owner_is_the_only_role_that_can_decide():
    """Cherry's core rule: recommend is a first-pass review, not an approval."""
    approvals = (Feature.APPROVE_LEAVE, Feature.APPROVE_DUTY_DO, Feature.APPROVE_SICK)
    for feature in approvals:
        assert can_decide(SystemRole.OWNER, feature)
        for role in SystemRole:
            if role is not SystemRole.OWNER:
                assert not can_decide(role, feature), f"{role.value} must not decide"


def test_recommend_roles_can_recommend_but_not_decide():
    for role in (SystemRole.NURSE_MGR, SystemRole.ADMIN_CLERK,
                 SystemRole.ALLIED_HEALTH):
        assert can_recommend(role, Feature.APPROVE_LEAVE)
        assert not can_decide(role, Feature.APPROVE_LEAVE)


def test_allied_health_recommends_only_within_its_own_domain():
    """The gap this used to document is closed.

    The v1 role table called ALLIED_HEALTH "PT/OT/ST; recommend within own
    domain" and then gave it `R` in no cell of either matrix. The old test
    followed the matrix and asserted no R anywhere, on the basis that the
    specific table beats the general sentence - and said in its docstring that if
    Cherry had meant otherwise it would fail loudly. It did, and she did:

        "Yes, my intention was for them to have R for leave/duty approvals within
         their own domain only (e.g. PT approving PT leave). For task codes and
         escort, E is perfectly fine."   - 1 Aug 2026
    """
    assert can_recommend(SystemRole.ALLIED_HEALTH, Feature.APPROVE_LEAVE)
    assert can_recommend(SystemRole.ALLIED_HEALTH, Feature.APPROVE_DUTY_DO)
    # ...but scoped, unlike every other R in the matrix.
    assert recommend_scope(SystemRole.ALLIED_HEALTH,
                           Feature.APPROVE_LEAVE) == "own_domain"
    assert recommend_scope(SystemRole.NURSE_MGR,
                           Feature.APPROVE_LEAVE) == "facility"
    # Unchanged by her answer: "for task codes and escort, E is perfectly fine."
    assert grant_for(SystemRole.ALLIED_HEALTH, Feature.TASK_CODES) is Grant.EDIT
    assert grant_for(SystemRole.ALLIED_HEALTH, Feature.MEDICAL_ESCORT) is Grant.VIEW
    # Not in her answer, so it stays shut.
    assert not can_recommend(SystemRole.ALLIED_HEALTH, Feature.APPROVE_SICK)


@pytest.mark.parametrize(("reviewer", "subject", "allowed"), [
    ("PT",  "PT",   True),    # Cherry's own example
    ("PT",  "PTA",  True),    # the assistant whose absence the PT has to cover
    ("PTA", "PT",   True),
    ("OT",  "OTA",  True),
    ("PT",  "OT",   False),   # a different profession, not "own domain"
    ("OT",  "PT",   False),
    ("PT",  "RN",   False),
    ("PT",  None,   False),   # unknown subject rank denies
    (None,  "PT",   False),   # reviewer not linked to a staff record denies
    ("PT",  "HCA",  False),
])
def test_the_domain_boundary(reviewer, subject, allowed):
    """Own domain is the discipline, not all of allied health. Cherry's example is
    a PT approving PT leave; an OT is a different profession and a PT has no
    standing over their caseload cover."""
    assert may_recommend_for(
        SystemRole.ALLIED_HEALTH, Feature.APPROVE_LEAVE,
        recommender_rank=reviewer, subject_rank=subject) is allowed


def test_facility_scoped_roles_ignore_domain():
    """A nursing officer recommends on anyone. Scoping is ALLIED_HEALTH's alone,
    and leaking it to the other R roles would quietly break the approval queue."""
    assert may_recommend_for(
        SystemRole.NURSE_MGR, Feature.APPROVE_LEAVE,
        recommender_rank="RN", subject_rank="PCW") is True
    assert may_recommend_for(
        SystemRole.ADMIN_CLERK, Feature.APPROVE_LEAVE,
        recommender_rank=None, subject_rank=None) is True


def test_roi_is_owner_only():
    assert can_read(SystemRole.OWNER, Feature.ROI)
    for role in SystemRole:
        if role is not SystemRole.OWNER:
            assert not can_read(role, Feature.ROI), f"{role.value} must not read ROI"
            assert not can_write(role, Feature.ROI)


def test_scheduler_drafts_but_never_publishes():
    assert can_write(SystemRole.SCHEDULER, Feature.ROSTER_AI_DRAFT)
    assert not can_write(SystemRole.SCHEDULER, Feature.ROSTER_PUBLISH)
    assert not can_read(SystemRole.SCHEDULER, Feature.ROI)
    assert not can_read(SystemRole.SCHEDULER, Feature.AUDIT_LOG)


def test_hr_auditor_is_read_only_except_certificates():
    assert can_write(SystemRole.HR_AUDITOR, Feature.CERTIFICATES)
    assert can_read(SystemRole.HR_AUDITOR, Feature.AUDIT_LOG)
    for feature in (Feature.ROSTER_PUBLISH, Feature.ROSTER_AI_DRAFT,
                    Feature.APPROVE_LEAVE, Feature.ROI, Feature.FACILITY_SETTINGS):
        assert not can_write(SystemRole.HR_AUDITOR, feature)


def test_self_only_is_not_a_facility_read():
    """`S` must not satisfy a facility-wide read - conflating them is how a care
    worker ends up holding the home's leave history."""
    assert is_self_only(SystemRole.FRONTLINE, Feature.APPROVE_LEAVE)
    assert not can_read(SystemRole.FRONTLINE, Feature.APPROVE_LEAVE)


def test_frontline_sees_no_management_module():
    hidden = visible_features(SystemRole.FRONTLINE)
    for feature in (Feature.DASHBOARD, Feature.ROI, Feature.REPORTS,
                    Feature.COMPLIANCE, Feature.AUDIT_LOG,
                    Feature.FACILITY_SETTINGS, Feature.ROSTER_PUBLISH):
        assert feature not in hidden, f"{feature.value} must be hidden from FRONTLINE"


# ── legacy role values keep working ─────────────────────────────────────────
@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("superintendent", SystemRole.OWNER),
        ("admin", SystemRole.ADMIN_CLERK),
        ("staff", SystemRole.FRONTLINE),
        ("scheduler", SystemRole.SCHEDULER),
        ("hr", SystemRole.HR_AUDITOR),
        ("auditor", SystemRole.HR_AUDITOR),
    ],
)
def test_legacy_role_values_resolve(legacy, canonical):
    assert normalise_role(legacy) is canonical
    assert grant_for(legacy, Feature.ROI) is grant_for(canonical, Feature.ROI)


@pytest.mark.parametrize("bad", [None, "", "   ", "nonsense", "ROOT"])
def test_unknown_roles_are_denied_everywhere(bad):
    for feature in Feature:
        assert grant_for(bad, feature) is Grant.NONE


# ── the guards ──────────────────────────────────────────────────────────────
def test_require_read_allows_and_denies():
    guard = require_read(Feature.DASHBOARD)
    assert guard(_ctx("NURSE_MGR")).profile.role == "NURSE_MGR"
    with pytest.raises(HTTPException) as exc:
        guard(_ctx("FRONTLINE"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "forbidden"


def test_require_write_refuses_a_view_grant():
    guard = require_write(Feature.REPORTS)
    assert guard(_ctx("OWNER"))
    for role in ("NURSE_MGR", "ADMIN_CLERK"):       # both hold V on reports
        with pytest.raises(HTTPException) as exc:
            guard(_ctx(role))
        assert exc.value.status_code == 403


def test_require_decide_refuses_recommend_roles():
    guard = require_decide(Feature.APPROVE_LEAVE)
    assert guard(_ctx("OWNER"))
    for role in ("NURSE_MGR", "ADMIN_CLERK", "ALLIED_HEALTH", "SCHEDULER",
                 "FRONTLINE", "HR_AUDITOR", "admin", "scheduler", "hr"):
        with pytest.raises(HTTPException) as exc:
            guard(_ctx(role))
        assert exc.value.status_code == 403, f"{role} must not decide leave"


def test_require_recommend_admits_r_roles_and_owner():
    guard = require_recommend(Feature.APPROVE_LEAVE)
    # ALLIED_HEALTH now passes the *route* guard. Whose request they may
    # recommend on is a separate check, in the service, against the data - the
    # router cannot answer it because it does not know whose leave this is.
    for role in ("OWNER", "NURSE_MGR", "ADMIN_CLERK", "ALLIED_HEALTH",
                 "superintendent", "admin"):
        assert guard(_ctx(role))
    for role in ("FRONTLINE", "staff", "SCHEDULER", "HR_AUDITOR"):
        with pytest.raises(HTTPException):
            guard(_ctx(role))


# ── regressions from Cherry's 2026-07-30 production testing ─────────────────
# Over HTTP, not by calling the handler: a guard is a FastAPI dependency, so
# invoking the function directly would skip it and pass while production leaks.
# `dependency_overrides[get_ctx]` swaps in a role without needing Supabase.

@pytest.fixture
def as_role():
    from api.main import app

    http = TestClient(app, raise_server_exceptions=False)

    def _as(role: str) -> TestClient:
        app.dependency_overrides[get_ctx] = lambda: _ctx(role)
        return http

    yield _as
    app.dependency_overrides.pop(get_ctx, None)


# The endpoints Cherry hit with a staff token and got 200 from.
STAFF_MUST_NOT_REACH = [
    "/roi/summary",
    "/roi/settings",
    "/dashboard/summary",
    "/reports",
    "/reports/types",
    "/reports/schedules",
    "/kpi/overview",
    "/kpi/an-gini",
    "/leave-requests/stats",
]


@pytest.mark.parametrize("path", STAFF_MUST_NOT_REACH)
def test_staff_token_is_refused(as_role, path):
    r = as_role("staff").get(path)
    assert r.status_code == 403, f"{path} returned {r.status_code} to a staff token"
    assert r.json()["detail"]["code"] == "forbidden"


def test_staff_token_cannot_write_the_roi_baseline(as_role):
    r = as_role("staff").put("/roi/settings", json={"agency_hourly_rate": 1})
    assert r.status_code == 403


def test_owner_still_reaches_roi(as_role):
    """The guard must not lock out the role that owns the feature. 403 is the
    failure being tested; any other status means the guard let the request
    through to the (unstubbed) database."""
    assert as_role("superintendent").get("/roi/summary").status_code != 403


def test_nurse_mgr_reaches_reports_but_not_roi(as_role):
    http = as_role("NURSE_MGR")
    assert http.get("/reports").status_code != 403
    assert http.get("/roi/summary").status_code == 403


def test_leave_list_narrows_to_own_rows_for_frontline(monkeypatch):
    """Was: a staff token listed the whole facility's leave requests."""
    seen: dict = {}

    def fake_list(client, facility_id, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(leave_router.svc, "list_requests", fake_list)
    monkeypatch.setattr(leave_router, "resolve_staff_id", lambda p: "own-staff-id")

    # Asking for someone else's rows is ignored, not honoured.
    leave_router.list_requests(None, None, None, None, None, None,
                              "another-staff-id", _ctx("staff"))
    assert seen["staff_id"] == "own-staff-id"


def test_leave_list_stays_facility_wide_for_a_manager(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(leave_router.svc, "list_requests",
                        lambda client, fid, **kw: seen.update(kw) or [])
    leave_router.list_requests(None, None, None, None, None, None,
                               None, _ctx("NURSE_MGR"))
    assert seen["staff_id"] is None


def test_allied_health_can_now_read_the_leave_queue(monkeypatch):
    """Reversed by Cherry's 1 Aug answer, and it has to be.

    R is a read grant as well as a recommend grant. A therapist who cannot open
    the queue cannot recommend on anything in it, so granting R on leave without
    granting the read would be a role that holds a permission it can never use.
    """
    seen = {}
    monkeypatch.setattr(leave_router.svc, "list_requests",
                        lambda client, fid, **kw: seen.update(kw) or [])
    leave_router.list_requests(None, None, None, None, None, None,
                               None, _ctx("ALLIED_HEALTH"))
    assert seen, "the service should have been reached"
    # Facility-wide, not self-only: the scoping is applied when they act on a
    # request, not when they read the list.
    assert seen["staff_id"] is None


def test_scheduler_and_hr_auditor_still_cannot_recommend_on_leave():
    """Confirmed by Cherry, 1 Aug: SCHEDULER "should NOT recommend on leave -
    they just draft"; HR_AUDITOR approves nothing."""
    for role in (SystemRole.SCHEDULER, SystemRole.HR_AUDITOR):
        for feature in (Feature.APPROVE_LEAVE, Feature.APPROVE_DUTY_DO,
                        Feature.APPROVE_SICK):
            assert not can_recommend(role, feature), f"{role.value} / {feature}"
            assert not can_decide(role, feature)


def test_hr_auditor_still_cannot_see_roi():
    """Confirmed by Cherry, 1 Aug: "HR_AUDITOR: Should NOT see ROI"."""
    assert not can_read(SystemRole.HR_AUDITOR, Feature.ROI)
    assert grant_for(SystemRole.HR_AUDITOR, Feature.ROI) is Grant.NONE


# ── the KPI matrix (Cherry's RBAC v2, 1 Aug 2026) ───────────────────────────
KPI_ROWS = [
    # (feature, OWNER, NURSE_MGR, ALLIED, CLERK, FRONTLINE, SCHEDULER, HR_AUDITOR)
    (Feature.KPI,                "F", "V", "-", "V", "-", "V", "V"),
    # The one that is different, and the correction to our own v1 guess.
    (Feature.KPI_STAFFING_RATIO, "F", "V", "-", "-", "-", "V", "V"),
]


@pytest.mark.parametrize(("feature", "owner", "nurse", "allied", "clerk",
                          "frontline", "scheduler", "auditor"), KPI_ROWS)
def test_the_kpi_matrix(feature, owner, nurse, allied, clerk, frontline,
                        scheduler, auditor):
    expected = {
        SystemRole.OWNER: owner, SystemRole.NURSE_MGR: nurse,
        SystemRole.ALLIED_HEALTH: allied, SystemRole.ADMIN_CLERK: clerk,
        SystemRole.FRONTLINE: frontline, SystemRole.SCHEDULER: scheduler,
        SystemRole.HR_AUDITOR: auditor,
    }
    for role, code in expected.items():
        assert grant_for(role, feature) is Grant(code), (
            f"{role.value} on {feature.value} should be {code}")


def test_staffing_ratio_is_narrower_than_compliance():
    """The v1 guess routed this endpoint through COMPLIANCE so a therapist could
    check whether the floor was legally staffed. Cherry overruled it. This test
    exists so the old reasoning cannot quietly return - it is a plausible
    argument, and it is not what the client decided."""
    assert can_read(SystemRole.ALLIED_HEALTH, Feature.COMPLIANCE)
    assert not can_read(SystemRole.ALLIED_HEALTH, Feature.KPI_STAFFING_RATIO)
    assert can_read(SystemRole.ADMIN_CLERK, Feature.COMPLIANCE)
    assert not can_read(SystemRole.ADMIN_CLERK, Feature.KPI_STAFFING_RATIO)
