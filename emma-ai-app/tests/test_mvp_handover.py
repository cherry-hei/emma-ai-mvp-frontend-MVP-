"""Staff PWA contract changes and the roster/incident audit call sites."""
from __future__ import annotations

import re
from datetime import date as Date, timedelta
from types import SimpleNamespace

import pytest

from api.routers import auth as auth_router
from api.routers import incidents as incidents_router
from api.routers import roster as roster_router
from emma_core.config import settings
from emma_core.models import CellWriteRequest, Profile
from emma_core.services import me as me_svc


# ── CORS ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("origin", [
    "https://main.d1abc2def3.amplifyapp.com",
    "https://staff-pwa.d1abc2def3.amplifyapp.com",
    "https://pr-42.d1abc2def3.amplifyapp.com",
])
def test_amplify_origins_are_allowed(origin):
    assert re.match(settings.allowed_origin_regex, origin)


@pytest.mark.parametrize("origin", [
    "https://evil.amplifyapp.com.attacker.example",
    "https://amplifyapp.com.attacker.example",
    "http://main.d1abc2def3.amplifyapp.com",
    "https://notamplifyapp.com",
])
def test_lookalike_origins_are_refused(origin):
    """An unanchored pattern hands CORS to anything ending in the domain."""
    assert not re.match(settings.allowed_origin_regex, origin)


def test_localhost_stays_in_the_explicit_allow_list():
    assert "http://localhost:3000" in settings.allowed_origins


def test_the_staff_pwa_origin_is_listed_exactly():
    assert "https://emmastaff-7p8bhd5l.manus.space" in settings.allowed_origins


@pytest.mark.parametrize("origin", [
    "https://attacker.manus.space",
    "https://emmastaff-7p8bhd5l.manus.space.attacker.example",
])
def test_other_manus_tenants_are_refused(origin):
    """Shared hosting, so neighbours must not inherit the staff app's access."""
    assert origin not in settings.allowed_origins
    assert not re.match(settings.allowed_origin_regex, origin)


def test_a_preview_pattern_is_still_anchored_when_the_deployment_supplies_one():
    """Widening the list for a preview host must not admit its lookalikes."""
    preview = settings.model_copy(update={
        "cors_origin_regex": r"https://[a-z0-9-]+\.trycloudflare\.com",
    })

    assert re.match(preview.allowed_origin_regex, "https://emma-pwa.trycloudflare.com")
    assert not re.match(preview.allowed_origin_regex,
                        "https://emma-pwa.trycloudflare.com.attacker.example")


def test_a_blank_regex_disables_pattern_matching_rather_than_allowing_everything():
    assert settings.model_copy(update={"cors_origin_regex": ""}).allowed_origin_regex is None


# ── login ───────────────────────────────────────────────────────────────────
def _session_and_profile():
    session = SimpleNamespace(
        access_token="at", refresh_token="rt", expires_at=1756598400,
        user=SimpleNamespace(id="8f3c", email="manager@naac.example"),
    )
    profile = Profile(
        id="p1", auth_user_id="8f3c", facility_id="fac1",
        email="manager@naac.example", role="superintendent", staff_id="b41e",
        facility={"code": "A", "name": "Care Home A"},
    )
    return session, profile


def test_both_shapes_agree_on_who_is_signed_in():
    out = auth_router._session_out(*_session_and_profile())

    assert out.user is not None
    assert out.user.id == out.user_id
    assert out.user.email == out.email
    assert out.user.role == out.role
    assert out.user.facility_id == out.facility_id
    assert out.user.facility_name == out.facility_name


def test_the_flat_fields_survive():
    out = auth_router._session_out(*_session_and_profile())

    assert out.access_token == "at"
    assert out.refresh_token == "rt"
    assert out.token_type == "bearer"
    assert out.user_id == "8f3c"
    assert out.facility_name == "Care Home A"


def test_staff_id_arrives_with_the_nested_user():
    out = auth_router._session_out(*_session_and_profile())

    assert out.user.staff_id == "b41e"
    assert not hasattr(out, "staff_id")


# ── /me/roster ──────────────────────────────────────────────────────────────
class _NullClient:
    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


@pytest.fixture
def roster_window(monkeypatch):
    """my_roster with the database stubbed out, so only the window is left."""
    monkeypatch.setattr(me_svc, "_my_shifts", lambda *a, **k: [])
    monkeypatch.setattr(me_svc, "_staff_row",
                        lambda *a, **k: {"id": "b41e", "name": "Chan", "rank": "CW"})
    monkeypatch.setattr(me_svc, "resolve_period", lambda *a, **k: None)

    def call(**kwargs):
        return me_svc.my_roster(_NullClient(), "fac1", "b41e", **kwargs)

    return call


def test_end_is_inclusive(roster_window):
    out = roster_window(start=Date(2026, 9, 1), end=Date(2026, 9, 7))

    assert out["start"] == "2026-09-01"
    assert out["end"] == "2026-09-07"
    assert len(out["days"]) == 7


def test_end_wins_over_days(roster_window):
    out = roster_window(start=Date(2026, 9, 1), end=Date(2026, 9, 3), days=30)

    assert out["end"] == "2026-09-03"
    assert len(out["days"]) == 3


def test_end_alone_anchors_on_today(roster_window):
    out = roster_window(end=Date.today() + timedelta(days=2))

    assert out["start"] == Date.today().isoformat()
    assert len(out["days"]) == 3


def test_a_date_range_cannot_out_reach_the_days_cap(roster_window):
    out = roster_window(start=Date(2026, 1, 1), end=Date(2027, 1, 1))

    assert len(out["days"]) == me_svc.MAX_ROSTER_DAYS


def test_end_before_start_is_rejected(roster_window):
    with pytest.raises(ValueError):
        roster_window(start=Date(2026, 9, 7), end=Date(2026, 9, 1))


def test_days_still_works(roster_window):
    out = roster_window(days=7)

    assert len(out["days"]) == 7
    assert out["start"] == Date.today().isoformat()


# ── audit ───────────────────────────────────────────────────────────────────
@pytest.fixture
def audit_rows(monkeypatch):
    rows: list[dict] = []

    def record(_client, **kwargs):
        rows.append(kwargs)
        return kwargs

    for module in (roster_router, incidents_router):
        monkeypatch.setattr(module.audit, "record", record)
    return rows


@pytest.fixture
def ctx():
    return SimpleNamespace(
        client=_NullClient(),
        facility_id="fac1",
        profile_id="p1",
        profile=Profile(id="p1", facility_id="fac1", email="boss@naac.example",
                        role="superintendent", staff_id="b41e"),
    )


def _cell_body():
    return CellWriteRequest(roster_version_id="v1", staff_id="b41e",
                            date=Date(2026, 9, 1), shift_type="A", tasks=["meal"])


@pytest.mark.parametrize("handler,action", [
    (roster_router.create_shift, "create"),
    (roster_router.edit_shift, "update"),
])
def test_a_cell_write_logs_the_action_it_was(
        monkeypatch, audit_rows, ctx, handler, action):
    """Adding a shift and changing one are different events to whoever reads this."""
    monkeypatch.setattr(roster_router.svc, "get_shift_defs",
                        lambda *a, **k: [SimpleNamespace(shift_type="A")])
    monkeypatch.setattr(roster_router.scheduling_svc, "validate_task_labels",
                        lambda *a, **k: None)
    monkeypatch.setattr(roster_router.svc, "set_cell", lambda *a, **k: "sa1")
    monkeypatch.setattr(roster_router.scheduling_svc,
                        "sync_task_rows_for_assignment", lambda *a, **k: None)

    handler(_cell_body(), ctx)

    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row["action"] == action
    assert row["entity_table"] == "shift_assignments"
    assert row["entity_id"] == "sa1"
    assert row["actor_profile_id"] == "p1"
    assert row["actor_email"] == "boss@naac.example"
    assert row["after"]["shift_type"] == "A"


def test_a_cleared_cell_is_logged_by_coordinates(monkeypatch, audit_rows, ctx):
    monkeypatch.setattr(roster_router.svc, "clear_cell", lambda *a, **k: None)

    roster_router.delete_shift(roster_version_id="v1", staff_id="b41e",
                               date=Date(2026, 9, 1), ctx=ctx)

    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row["action"] == "delete"
    assert row["entity_table"] == "shift_assignments"
    assert row["before"]["roster_version_id"] == "v1"
    assert row["before"]["staff_id"] == "b41e"


def test_a_new_period_is_logged(monkeypatch, audit_rows, ctx):
    monkeypatch.setattr(
        roster_router.svc, "create_period",
        lambda *a, **k: ({"id": "per1", "period_start": "2026-09-01",
                          "period_end": "2026-09-28", "cycle_type": "4week"},
                         {"id": "ver1"}))

    body = roster_router.PeriodCreateRequest(
        period_start=Date(2026, 9, 1), period_end=Date(2026, 9, 28))
    roster_router.create_period(body, ctx)

    assert [r["entity_table"] for r in audit_rows] == ["roster_periods"]
    assert audit_rows[0]["action"] == "create"
    assert audit_rows[0]["entity_id"] == "per1"


def test_calling_in_sick_is_logged(monkeypatch, audit_rows, ctx):
    monkeypatch.setattr(incidents_router.svc, "open_incident",
                        lambda *a, **k: {"id": "inc1"})
    monkeypatch.setattr(incidents_router, "resolve_staff_id", lambda _p: "b41e")

    body = incidents_router.IncidentCreate(
        staff_id="b41e", incident_type="sick_leave", date=Date(2026, 9, 1))
    incidents_router.create_incident(body, ctx)

    assert len(audit_rows) == 1
    assert audit_rows[0]["entity_table"] == "sl_incidents"
    assert audit_rows[0]["action"] == "create"
    assert audit_rows[0]["entity_id"] == "inc1"


def test_assigning_cover_logs_the_swap_and_the_hours_owed(
        monkeypatch, audit_rows, ctx):
    monkeypatch.setattr(incidents_router.svc, "get_incident",
                        lambda *a, **k: {"replacement_status": "open",
                                         "replacement_staff_id": None})
    monkeypatch.setattr(incidents_router.svc, "resolve_incident", lambda *a, **k: {
        "incident": {"replacement_status": "resolved",
                     "replacement_staff_id": "cover1", "auto_resolved": False},
        "future_debts": [{"debt_type": "TOIL", "quantity": 8.0, "unit": "hours"}],
        "resolution_minutes": 12,
    })

    body = incidents_router.IncidentResolveRequest(replacement_staff_id="cover1")
    incidents_router.resolve_incident("inc1", body, ctx)

    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row["action"] == "update"
    assert row["before"]["replacement_status"] == "open"
    assert row["after"]["replacement_status"] == "resolved"
    assert row["after"]["replacement_staff_id"] == "cover1"
    assert row["after"]["resolution_minutes"] == 12
    assert row["after"]["future_debts"] == [
        {"debt_type": "TOIL", "quantity": 8.0, "unit": "hours"}]


def test_the_routers_do_not_guard_the_audit_write_themselves(monkeypatch, ctx):
    """audit.record swallows its own failures. If this stops raising, that moved."""
    monkeypatch.setattr(roster_router.svc, "clear_cell", lambda *a, **k: None)

    def boom(*_a, **_k):
        raise RuntimeError("audit_logs unreachable")

    monkeypatch.setattr(roster_router.audit, "record", boom)

    with pytest.raises(RuntimeError):
        roster_router.delete_shift(roster_version_id="v1", staff_id="b41e",
                                   date=Date(2026, 9, 1), ctx=ctx)


# ── roster period dates ─────────────────────────────────────────────────────
def test_a_backwards_period_is_refused():
    """It reads as an empty period, and the grid then looks like it lost shifts."""
    from emma_core.services import roster as roster_svc

    with pytest.raises(ValueError):
        roster_svc.create_period(_NullClient(), facility_id="fac1",
                                 period_start=Date(2026, 10, 1),
                                 period_end=Date(2026, 9, 30))


def test_a_single_day_period_is_still_allowed():
    from emma_core.services import roster as roster_svc

    with pytest.raises(Exception) as exc:
        roster_svc.create_period(_NullClient(), facility_id="fac1",
                                 period_start=Date(2026, 10, 1),
                                 period_end=Date(2026, 10, 1))
    assert "period_end" not in str(exc.value)
