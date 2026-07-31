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
    normalise_role,
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
    (Feature.APPROVE_LEAVE,       "F", "R", "-", "R", "S"),
    (Feature.APPROVE_DUTY_DO,     "F", "R", "-", "R", "S"),
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
    for role in (SystemRole.NURSE_MGR, SystemRole.ADMIN_CLERK):
        assert can_recommend(role, Feature.APPROVE_LEAVE)
        assert not can_decide(role, Feature.APPROVE_LEAVE)
    assert not can_recommend(SystemRole.ALLIED_HEALTH, Feature.APPROVE_LEAVE)


def test_allied_health_holds_no_recommend_grant_anywhere():
    """Documents a gap, deliberately.

    The role table calls ALLIED_HEALTH "PT/OT/ST; recommend within own domain",
    but no row of either feature matrix grants it `R` - its grants are only V, E
    or hidden. The matrix is followed here because it is the more specific
    statement; if Cherry intended R on the therapy-domain rows (task codes,
    medical escort), those cells need to change and this test will fail, which is
    how we will notice.
    """
    assert not any(
        can_recommend(SystemRole.ALLIED_HEALTH, f)
        for f in Feature
    )
    assert grant_for(SystemRole.ALLIED_HEALTH, Feature.TASK_CODES) is Grant.EDIT
    assert grant_for(SystemRole.ALLIED_HEALTH, Feature.MEDICAL_ESCORT) is Grant.VIEW


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
    for role in ("OWNER", "NURSE_MGR", "ADMIN_CLERK", "superintendent", "admin"):
        assert guard(_ctx(role))
    for role in ("ALLIED_HEALTH", "FRONTLINE", "staff"):
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


def test_allied_health_cannot_list_leave_at_all(monkeypatch):
    monkeypatch.setattr(leave_router.svc, "list_requests",
                        lambda *a, **k: pytest.fail("service must not be reached"))
    with pytest.raises(HTTPException) as exc:
        leave_router.list_requests(None, None, None, None, None, None,
                                   None, _ctx("ALLIED_HEALTH"))
    assert exc.value.status_code == 403
