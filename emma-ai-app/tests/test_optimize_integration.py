"""Integration test: the Phase 2 solver writeback against the REAL seeded DB.

This complements the offline fake-client tests in ``test_optimize_service.py``.
Those map DB<->dataclasses through an in-memory stub, so they pass even when the
solver migration (``...0004_solver_phase2.sql``) was never applied to the running
database. This test runs the optimizer against the *actual* Postgres and fails
loudly if ``optimization_jobs`` / ``roster_option_scores`` / ``violation_log`` are
missing — the exact regression the offline suite cannot see (found 2026-07-23).

Skips (does not fail) only when no local Supabase is reachable, so the offline
suite still runs standalone. When the DB *is* up but the Phase 2 tables are
absent, the tables-exist test fails — that is the point.
"""
from __future__ import annotations

import pytest

from emma_core.constants import JobStatus, PlanMode
from emma_core.models import OptimizeRequest
from emma_core.services import optimize

PHASE2_TABLES = ["optimization_jobs", "roster_option_scores", "violation_log"]

# Reachability probe: a base table that predates Phase 2. If this fails the DB is
# down/unconfigured and we skip; if it succeeds the DB is up and Phase 2 tables
# are expected to exist (their absence is a real failure, not a skip).
try:
    from emma_core.db import get_service_client

    _sb = get_service_client()
    # SQL: select id from facilities limit 1   -- reachability probe, result unused
    _sb.table("facilities").select("id").limit(1).execute()
except Exception:  # noqa: BLE001 — no DB to integrate against
    _sb = None

pytestmark = pytest.mark.skipif(_sb is None, reason="local Supabase not reachable")


def _home_a_manual():
    # SQL: select id from facilities where code = 'A'
    fid = _sb.table("facilities").select("id").eq("code", "A").execute().data[0]["id"]
    # SQL: select * from roster_versions
    #      where facility_id = :fid and version_type = 'manual'
    #      order by created_at desc
    #      limit 1
    mv = (_sb.table("roster_versions").select("*")
          .eq("facility_id", fid).eq("version_type", "manual")
          .order("created_at", desc=True).limit(1).execute().data)
    return fid, (mv[0] if mv else None)


def _cleanup(resp) -> None:
    """Return the DB to its seeded baseline. Deleting each auto roster_versions
    row cascades to its shifts/shift_assignments and to roster_option_scores /
    violation_log (all ON DELETE CASCADE); the job row is deleted separately."""
    for o in resp.roster_options:
        if o.roster_version_id:
            # SQL: delete from roster_versions where id = :roster_version_id
            # (shifts / assignments / scores cascade off the version)
            _sb.table("roster_versions").delete().eq("id", o.roster_version_id).execute()
    # SQL: delete from optimization_jobs where id = :job_id
    _sb.table("optimization_jobs").delete().eq("id", resp.job_id).execute()


def test_phase2_tables_exist():
    """The solver migration must be applied. A missing table raises PostgREST's
    APIError here — catching the 'migration authored but never applied' gap."""
    for t in PHASE2_TABLES:
        # SQL: select * from <t> limit 1   -- existence probe; a missing table errors
        _sb.table(t).select("*").limit(1).execute()


def test_run_optimization_persists_against_real_db():
    fid, manual = _home_a_manual()
    assert manual, "expected a seeded manual roster for Home A"

    resp = optimize.run_optimization(
        _sb, OptimizeRequest(facility_id=fid, period_id=manual["period_id"]))
    try:
        assert resp.status == JobStatus.COMPLETED
        assert {o.plan_mode for o in resp.roster_options} == {PlanMode.A, PlanMode.B, PlanMode.C}

        job = optimize.get_job(_sb, resp.job_id)
        assert job and job["status"] == JobStatus.COMPLETED

        version_ids = [o.roster_version_id for o in resp.roster_options if o.roster_version_id]
        assert version_ids, "at least one option should persist a roster version"
        # SQL: select id from roster_option_scores
        #      where roster_version_id = any(:version_ids)
        scores = (_sb.table("roster_option_scores").select("id")
                  .in_("roster_version_id", version_ids).execute().data)
        assert len(scores) == len(version_ids)
    finally:
        _cleanup(resp)


def test_manual_view_not_shadowed_by_auto_drafts():
    """After generating A/B/C, get_roster_grid must still return the manual roster."""
    from emma_core.services.roster import get_roster_grid

    fid, manual = _home_a_manual()
    assert manual
    resp = optimize.run_optimization(
        _sb, OptimizeRequest(facility_id=fid, period_id=manual["period_id"]))
    try:
        grid = get_roster_grid(_sb, fid, manual["period_id"])
        assert grid.version_id == manual["id"]
    finally:
        _cleanup(resp)
