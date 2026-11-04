"""Staff accounts must not reach facility-wide manager features."""

import pytest

from api.deps import AuthCtx, get_ctx
from api.main import app
from emma_core.models import Profile
from emma_core.services import ai_compliance, ai_gateway, audit
from fastapi.testclient import TestClient


def test_staff_cannot_query_compliance_suggestions_or_download_exports():
    ctx = AuthCtx(
        token="synthetic",
        client=None,
        profile=Profile(
            id="synthetic-profile", role="staff", facility_id="synthetic-facility"
        ),
    )
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_ctx] = lambda: ctx
    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/ai/compliance-qa", json={"question": "staffing ratio"}
                ).status_code
                == 403
            )
            assert (
                client.get("/exports/naac/tahduty.xlsx?period_id=synthetic").status_code
                == 403
            )
            assert (
                client.get("/sl-incidents/synthetic/ai-suggestion").status_code == 403
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_a_manager_cannot_enable_external_ai_for_an_unlisted_tenant(monkeypatch):
    monkeypatch.setattr(ai_gateway.settings, "bedrock_enabled", True)
    monkeypatch.setattr(ai_gateway.settings, "ai_synthetic_facility_ids", "approved-synthetic")
    monkeypatch.setattr(ai_gateway.BedrockProvider, "complete", lambda *a, **k: pytest.fail("External AI must stay off"))
    monkeypatch.setitem(ai_compliance.CHECKS, "staffing_ratio", lambda *a: (
        "compliant", {"date": "2026-11-03", "passing": 1, "total": 1, "checks": [], "failing": []}
    ))
    monkeypatch.setattr(audit, "record", lambda *a, **k: None)
    ctx = AuthCtx(token="synthetic", client=None,
                  profile=Profile(id="manager", role="OWNER", facility_id="unlisted-tenant"))
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_ctx] = lambda: ctx
    try:
        with TestClient(app) as client:
            status = client.get("/ai/status").json()
            assert status["providers"] == ["offline"]
            assert not status["bedrock_enabled"]
            response = client.post("/ai/compliance-qa", json={
                "question": "staffing ratio", "date": "2026-11-03",
                "facility_id": "approved-synthetic",
            })
            assert response.status_code == 200
            assert response.json()["verdict"] == "compliant"
            assert not response.json()["explained"]
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)
