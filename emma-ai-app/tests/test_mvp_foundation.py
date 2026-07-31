"""MVP foundation tests: audit trail, calendar, configs, governance, reports.

Split the same way as the rest of the suite:
  • Offline: the documented API surface and the pure guards on the new services.
  • DB-backed: real login -> RLS-scoped calls. Skips cleanly when no database is
    reachable.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests._dbstate import require

client = TestClient(app, raise_server_exceptions=False)


# ── offline: the surface the delivery plan lists ─────────────────────────────
def test_openapi_documents_the_mvp_foundation_surface():
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        # 1.4 data import
        "/imports": ("get",), "/imports/roster-excel": ("post",),
        "/imports/{job_id}": ("get",), "/imports/layouts": ("get",),
        # 1.5 calendar
        "/calendar-days": ("get", "post"),
        # 2.2 / 2.3 facility configuration and the shift dictionary
        "/facility-configs": ("get", "post"), "/shift-definitions": ("get", "post"),
        # 1.3 audit trail
        "/audit-logs": ("get",),
        # 0.1 / 0.2 governance records
        "/architecture-decisions": ("get",), "/project-scope": ("get",),
        # 1.6 evidence checklist
        "/evidence-items": ("get",),
    }
    missing = {path: verbs for path, verbs in expected.items()
               if path not in paths
               or any(verb not in paths[path] for verb in verbs)}
    assert not missing, f"missing from OpenAPI: {missing}"


def test_named_report_endpoints_cover_phase_seven():
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/reports/{name}"]
    from api.routers.reports import NAMED_REPORTS

    assert set(NAMED_REPORTS) == {"compliance", "roster", "staffing-ratio", "evidence"}
    from emma_core.services import reports as svc

    for report_type in NAMED_REPORTS.values():
        assert report_type in svc.GENERATORS and report_type in svc.TITLES


def test_foundation_routes_require_a_bearer_token():
    for path in ("/imports", "/calendar-days", "/facility-configs", "/audit-logs",
                 "/architecture-decisions", "/project-scope", "/evidence-items"):
        assert client.get(path).status_code == 401, path


# ── offline: pure guards on the new services ─────────────────────────────────
def test_calendar_day_type_is_validated():
    from emma_core.services.calendar_days import DAY_TYPES, upsert_day

    with pytest.raises(ValueError, match="day_type"):
        upsert_day(None, "f", date="2026-01-01", day_type="bank_holiday")
    assert "statutory_holiday" in DAY_TYPES and "special_pay" in DAY_TYPES


def test_facility_config_rejects_a_non_object_payload():
    from emma_core.services.facility_config import put_config

    with pytest.raises(ValueError, match="must be an object"):
        put_config(None, "f", config_key="scheduling_cycle", config_json=[1, 2])
    with pytest.raises(ValueError, match="config_key"):
        put_config(None, "f", config_key="", config_json={})


def test_shift_definition_segments_are_validated():
    from emma_core.services.facility_config import upsert_shift_definition

    with pytest.raises(ValueError, match="HH:MM"):
        upsert_shift_definition(None, "f", shift_type="AN",
                                segments=[{"start": "7", "end": "13:30"}])
    with pytest.raises(ValueError, match="segment"):
        upsert_shift_definition(None, "f", shift_type="AN", segments=[{"start": "07:00"}])


def test_evidence_status_is_validated():
    from emma_core.services.governance import EVIDENCE_STATUSES, set_evidence_status

    with pytest.raises(ValueError, match="status"):
        set_evidence_status(None, "f", "EV-01", status="probably")
    assert set(EVIDENCE_STATUSES) == {"pending", "pass", "fail", "not_applicable"}


def test_evidence_caveats_do_not_over_claim():
    """The submission wording the delivery plan requires, kept with the data.

    Phase 8.2 names the exact risks: promising unconditional deletion, fixing an
    AI vendor, asserting critical-infrastructure status, or claiming TLS 1.3 only.
    """
    from emma_core.services.governance import EVIDENCE_CAVEATS

    text = " ".join(EVIDENCE_CAVEATS).lower()
    assert "pdpo" in text and "not unconditional" in text
    assert "7-year" in text and "confirmation" in text
    assert "no vendor is fixed" in text
    assert "tls 1.2 minimum" in text and "tls 1.3 where supported" in text
    assert "if required" in text and "not asserted to be critical" in text
    assert "external qualified reviewer" in text


def test_import_service_rejects_unknown_mode_and_variant():
    from emma_core.services.imports import MODES, VARIANTS, run_import

    with pytest.raises(ValueError, match="mode"):
        run_import(None, None, "f", filename="x.xlsx", content=b"", mode="delete")
    with pytest.raises(ValueError, match="variant"):
        run_import(None, None, "f", filename="x.xlsx", content=b"", mode="validate",
                   variant="sideways")
    assert MODES == ("validate", "commit") and set(VARIANTS) == {"after", "before"}


# ── DB-backed ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token():
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in("super_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable/seeded: {exc}")
    return session.access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_architecture_decision_is_recorded(token):
    rows = require(client.get("/architecture-decisions", headers=_auth(token)).json(),
                   "architecture decision records")
    adr = rows[0]
    assert adr["code"].startswith("ADR-")
    assert adr["decision"] and adr["non_negotiables_json"]
    assert adr["alternatives_json"], "a decision record should say what was rejected"

    one = client.get(f'/architecture-decisions/{adr["code"]}', headers=_auth(token))
    assert one.status_code == 200 and one.json()["code"] == adr["code"]
    assert client.get("/architecture-decisions/ADR-9999",
                      headers=_auth(token)).status_code == 404


def test_mvp_scope_is_locked(token):
    summary = client.get("/project-scope/summary", headers=_auth(token)).json()
    assert summary["mvp_items"] > 0 and summary["deferred_items"] > 0
    rows = client.get("/project-scope", params={"scope": "mvp"},
                      headers=_auth(token)).json()
    assert rows and all(r["scope"] == "mvp" for r in rows)
    # The MVP is Phase 0-4 plus Phase 7 reporting; Phase 6 is not in it.
    phases = {r["phase"] for r in rows}
    assert any("Phase 7" in p for p in phases)
    assert not any("Phase 6" in p for p in phases)


def test_evidence_checklist_carries_counts_and_caveats(token):
    body = client.get("/evidence-items", headers=_auth(token)).json()
    assert body["items"] and body["caveats"]
    assert sum(body["counts"].values()) == len(body["items"])
    assert all({"code", "category", "title", "status"} <= set(i) for i in body["items"])


def test_calendar_days_round_trip(token):
    created = client.post("/calendar-days", headers=_auth(token), json={
        "day_date": "2026-12-25", "day_type": "public_holiday",
        "holiday_name": "pytest Christmas", "staff_cost_multiplier": 2.0,
    })
    assert created.status_code == 201
    row = created.json()
    assert row["day_type"] == "public_holiday" and float(row["staff_cost_multiplier"]) == 2.0
    try:
        listed = client.get("/calendar-days",
                            params={"date_from": "2026-12-01", "date_to": "2026-12-31"},
                            headers=_auth(token)).json()
        assert any(d["holiday_name"] == "pytest Christmas" for d in listed)
        # Re-posting the same date replaces rather than duplicates.
        again = client.post("/calendar-days", headers=_auth(token), json={
            "day_date": "2026-12-25", "day_type": "statutory_holiday",
        })
        assert again.status_code == 201 and again.json()["id"] == row["id"]
    finally:
        from emma_core.db import get_service_client

        (get_service_client().table("calendar_days")
         .delete().eq("id", row["id"]).execute())


def test_facility_config_versions_instead_of_overwriting(token):
    key = "pytest_probe"
    first = client.post("/facility-configs", headers=_auth(token),
                        json={"config_key": key, "config_json": {"round": 1}})
    assert first.status_code == 201 and first.json()["version"] == 1
    second = client.post("/facility-configs", headers=_auth(token),
                         json={"config_key": key, "config_json": {"round": 2}})
    assert second.status_code == 201 and second.json()["version"] == 2
    try:
        active = client.get("/facility-configs", params={"config_key": key},
                            headers=_auth(token)).json()
        assert [r["version"] for r in active] == [2], "only one version stays active"
        history = client.get("/facility-configs",
                             params={"config_key": key, "include_history": True},
                             headers=_auth(token)).json()
        assert [r["version"] for r in history] == [2, 1]
    finally:
        from emma_core.db import get_service_client

        (get_service_client().table("facility_json_configs")
         .delete().eq("config_key", key).execute())


def test_imported_facility_config_describes_the_source_roster(token):
    """The importer records what the workbook says the facility looks like."""
    rows = client.get("/facility-configs", params={"config_key": "scheduling_cycle"},
                      headers=_auth(token)).json()
    config = require(rows, "an imported scheduling_cycle config")[0]["config_json"]
    assert config["cycle_type"] in ("28day", "natural_month")
    assert config["cycle_days"] > 0


def test_audit_log_is_append_only(token):
    """Recording an auditable change appends a row that cannot then be rewritten."""
    from emma_core.db import get_service_client

    logs = require(client.get("/audit-logs", params={"limit": 5},
                              headers=_auth(token)).json(),
                   "audit log entries")
    row = logs[0]
    assert {"action", "entity_table", "created_at"} <= set(row)

    sb = get_service_client()
    with pytest.raises(Exception, match="append-only"):
        sb.table("audit_logs").update({"reason": "tampered"}).eq("id", row["id"]).execute()
    with pytest.raises(Exception, match="append-only"):
        sb.table("audit_logs").delete().eq("id", row["id"]).execute()


def test_audit_log_is_not_readable_by_a_staff_login():
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in("staff_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable/seeded: {exc}")
    r = client.get("/audit-logs",
                   headers={"Authorization": f"Bearer {session.access_token}"})
    assert r.status_code == 403


def test_import_jobs_record_what_was_loaded(token):
    jobs = require(client.get("/imports", headers=_auth(token)).json(),
                   "roster import jobs")
    job = client.get(f'/imports/{jobs[0]["id"]}', headers=_auth(token)).json()
    assert job["source_layout"] in ("home_a_duty_roster", "home_b_floor_roster")
    assert job["status"] == "completed" and job["source_sha256"]
    summary = job["summary_json"]
    assert summary["cells_parsed"] > 0 and summary["staff_rows"] > 0
    assert "load" in summary, "the summary should record what was written"
    assert isinstance(job["issues"], list)


def test_roster_export_report_carries_task_codes_and_events(token):
    report = client.post("/reports/roster", headers=_auth(token), json={})
    assert report.status_code == 201
    payload = report.json()["payload"]
    keys = {c["key"] for c in payload["columns"]}
    assert {"date", "staff", "shift_type", "paid_hours", "tasks", "events"} <= keys
    require(payload["rows"], "a rostered period to export")
    assert payload["meta"]["cells"] == len(payload["rows"])


def test_evidence_report_keeps_its_caveats(token):
    report = client.post("/reports/evidence", headers=_auth(token), json={})
    assert report.status_code == 201
    payload = report.json()["payload"]
    assert payload["rows"] and payload["meta"]["caveats"]
    assert all(r["status"] in ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE")
               for r in payload["rows"])


def test_unknown_named_report_is_a_404(token):
    r = client.post("/reports/not-a-report", headers=_auth(token), json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "unknown_report"
