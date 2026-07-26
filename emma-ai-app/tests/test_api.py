"""HTTP-level tests for the FastAPI surface.

Split in two:
  • Offline (no DB): app wiring, OpenAPI surface, the bearer-token auth guard and
    the JWT `sub` extractor — always run.
  • DB-backed: real login → token → RLS-scoped endpoint calls. These need the
    seeded local Supabase (`supabase start` + `scripts/seed.py`); they skip
    cleanly when it isn't reachable.
"""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from api.deps import _jwt_sub
from api.main import app

# raise_server_exceptions=False → unexpected server errors come back as real 500
# responses (as over HTTP), instead of re-raising into the test process.
client = TestClient(app, raise_server_exceptions=False)


# ── offline: wiring + auth guard ─────────────────────────────────────────────
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_documents_phase2_surface():
    paths = client.get("/openapi.json").json()["paths"]
    expected = [
        "/auth/login", "/auth/refresh", "/auth/me",
        "/roster-periods", "/roster-versions", "/rosters/{period_id}",
        "/shift-definitions", "/task-definitions", "/shifts",
        "/units", "/resident-counts", "/compliance/ratio", "/staff",
        "/optimize-roster", "/optimization-jobs/{job_id}",
        "/roster-option-scores/{roster_version_id}",
        "/roster-option-scores/compare/{period_id}", "/validate-roster",
    ]
    missing = [p for p in expected if p not in paths]
    assert not missing, f"missing from OpenAPI: {missing}"


def test_protected_route_requires_bearer():
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthorized"


def test_malformed_bearer_rejected():
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def _fake_jwt(sub: str) -> str:
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f'{seg({"alg": "HS256"})}.{seg({"sub": sub})}.sig'


def test_jwt_sub_extraction():
    assert _jwt_sub(_fake_jwt("auth-user-123")) == "auth-user-123"
    assert _jwt_sub("garbage") is None
    assert _jwt_sub("only.two") is None


# ── DB-backed: real token + RLS-scoped calls (skip without seeded Supabase) ──
@pytest.fixture(scope="module")
def token():
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in("super_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local Supabase not reachable/seeded: {exc}")
    return session.access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def session():
    from emma_core.services.auth import sign_in
    try:
        _, s = sign_in("super_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local Supabase not reachable/seeded: {exc}")
    return s


def test_refresh_rotates_session(session):
    r = client.post("/auth/refresh", json={"refresh_token": session.refresh_token})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["facility_name"]
    # the freshly minted access token authenticates /auth/me
    me = client.get("/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "superintendent"


def test_refresh_rejects_bad_token(session):
    # the session fixture proves Supabase is reachable; a bogus refresh token → 401.
    r = client.post("/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_failed"


def test_me_returns_profile(token):
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "superintendent"
    assert body["facility_id"]


def test_periods_and_grid(token):
    h = _auth(token)
    periods = client.get("/roster-periods", headers=h).json()
    assert isinstance(periods, list)
    if periods:
        grid = client.get(f"/rosters/{periods[0]['id']}", headers=h).json()
        assert "rows" in grid and "dates" in grid


def test_shift_definitions(token):
    defs = client.get("/shift-definitions", headers=_auth(token))
    assert defs.status_code == 200 and isinstance(defs.json(), list)


def test_task_definitions(token):
    r = client.get("/task-definitions", headers=_auth(token))
    if r.status_code == 500 and "task_definitions" in r.text:
        pytest.skip("migration 0005 (task_definitions) not applied to this DB")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_staff_directory(token):
    r = client.get("/staff", headers=_auth(token))
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and rows
    s = rows[0]
    for k in ("id", "name", "rank", "scheduled_hours", "contracted_period_hours", "status", "certs"):
        assert k in s, f"missing enriched field: {k}"


def test_staff_exposes_cert_expiry(token):
    # Certifications compliance view relies on cert_type + expiry_date per staff.
    rows = client.get("/staff", headers=_auth(token)).json()
    certs = [c for s in rows for c in s.get("certificates", [])]
    assert certs, "expected seeded certificates"
    assert all("cert_type" in c for c in certs)
    assert any(c.get("expiry_date") for c in certs), "expected at least one cert with an expiry date"


def test_staff_detail(token):
    rows = client.get("/staff", headers=_auth(token)).json()
    r = client.get(f"/staff/{rows[0]['id']}", headers=_auth(token))
    assert r.status_code == 200
    assert "shift_history" in r.json()
    missing = client.get("/staff/00000000-0000-0000-0000-000000000000", headers=_auth(token))
    assert missing.status_code == 404


def test_compliance_ratio_shape(token):
    r = client.get("/compliance/ratio", params={"date": "2026-07-01"}, headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_optimize_sync_path(token):
    """End-to-end Phase 2 over HTTP: POST /optimize-roster?sync=true drives the
    CP-SAT solver and returns a scored option. persist=false keeps it side-effect
    free (single plan C, tiny time budget) so the seeded roster is untouched."""
    h = _auth(token)
    me = client.get("/auth/me", headers=h).json()

    target = None
    for p in client.get("/roster-periods", headers=h).json():
        versions = client.get("/roster-versions", params={"period_id": p["id"]}, headers=h).json()
        if any(v["version_type"] == "manual" for v in versions):
            target = p["id"]
            break
    if not target:
        pytest.skip("no seeded manual roster to optimize")

    body = {
        "facility_id": me["facility_id"],           # router overrides from the token anyway
        "period_id": target,
        "plan_mode": "C",
        "solver_limits": {"max_seconds": 5, "workers": 4, "seed": 42},
        "writeback": {"persist": False},
    }
    r = client.post("/optimize-roster", params={"sync": "true"}, json=body, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["roster_options"]) == 1
    option = data["roster_options"][0]
    assert option["plan_mode"] == "C"
    assert isinstance(option["constraint_score"], int)

    # tidy the audit job row (run_optimization records one even with persist=False)
    try:
        from emma_core.db import get_service_client
        get_service_client().table("optimization_jobs").delete().eq("id", data["job_id"]).execute()
    except Exception:  # noqa: BLE001 — cleanup best-effort
        pass


def test_optimize_rejects_cross_facility_source_version(token):
    """Security regression: a Home A caller must not be able to seed an optimize
    from a Home B roster version (the service-role solver would otherwise copy
    Home B's demand into a Home A option)."""
    from emma_core.db import get_service_client
    sb = get_service_client()
    fac_b = sb.table("facilities").select("id").eq("code", "B").execute().data
    if not fac_b:
        pytest.skip("no Home B facility seeded")
    ver_b = (sb.table("roster_versions").select("id")
             .eq("facility_id", fac_b[0]["id"]).limit(1).execute().data)
    if not ver_b:
        pytest.skip("no Home B roster version seeded")

    h = _auth(token)  # super_a → Home A
    periods_a = client.get("/roster-periods", headers=h).json()
    if not periods_a:
        pytest.skip("no Home A period seeded")

    body = {
        "facility_id": "x",                       # overridden from the token
        "period_id": periods_a[0]["id"],          # a valid Home A period
        "source_version_id": ver_b[0]["id"],      # a Home B version — the attack
        "plan_mode": "C",
        "writeback": {"persist": False},
    }
    r = client.post("/optimize-roster", params={"sync": "true"}, json=body, headers=h)
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "not_found"
