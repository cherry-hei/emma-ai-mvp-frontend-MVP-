"""Run the new migrations and synthetic fixtures on the configured server, then roll back.

Enable explicitly with EMMA_RUN_SERVER_TESTS=1. No database is created and no
fixture or schema changes are committed by this module.
"""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from emma_core.config import settings
from psycopg.rows import dict_row

pytestmark = pytest.mark.skipif(
    os.getenv("EMMA_RUN_SERVER_TESTS") != "1",
    reason="set EMMA_RUN_SERVER_TESTS=1 to verify against the configured server",
)


@pytest.fixture(scope="module")
def server():
    conn = psycopg.connect(
        settings.database_url, connect_timeout=15, row_factory=dict_row
    )
    try:
        conn.execute("select set_config('lock_timeout','5s',true)")
        conn.execute("select set_config('statement_timeout','30s',true)")
        conn.execute("select set_config('request.jwt.claim.role','service_role',true)")
        conn.execute(
            "select set_config('request.jwt.claims','{\"role\":\"service_role\"}',true)"
        )
        for name in (
            "20261030000024_leave_roster_sync.sql",
            "20261030000025_event_staff_selection.sql",
        ):
            if name.startswith("20261030000024"):
                exists = conn.execute(
                    "select to_regclass('public.leave_roster_changes') is not null as present"
                ).fetchone()["present"]
            else:
                exists = conn.execute(
                    "select exists(select 1 from information_schema.columns where table_schema='public' and table_name='facility_events' and column_name='assigned_staff_ids') as present"
                ).fetchone()["present"]
            if not exists:
                conn.execute(
                    (
                        Path(__file__).parents[1] / "supabase" / "migrations" / name
                    ).read_text(encoding="utf-8")
                )
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def home(server):
    with server.transaction():
        code = "VERIFY_" + uuid4().hex[:10]
        org = server.execute(
            "insert into organisations(code,name) values(%s,'Synthetic verification') returning id",
            (code,),
        ).fetchone()["id"]
        facility = server.execute(
            "insert into facilities(code,name,org_id) values(%s,'Synthetic verification',%s) returning id",
            (code, org),
        ).fetchone()["id"]
        staff = server.execute(
            "insert into staff(facility_id,name,rank,employment_type) values(%s,'Invented RN','RN','local_ft') returning id",
            (facility,),
        ).fetchone()["id"]
        peer = server.execute(
            "insert into staff(facility_id,name,rank,employment_type) values(%s,'Invented peer','RN','local_ft') returning id",
            (facility,),
        ).fetchone()["id"]
        for shift_type, working in (("A7", True), ("AL", True), ("O", False)):
            server.execute(
                "insert into shift_definitions(facility_id,shift_type,is_working,paid_minutes) values(%s,%s,%s,%s)",
                (facility, shift_type, working, 480 if working else 0),
            )
        period = server.execute(
            "insert into roster_periods(facility_id,period_start,period_end) values(%s,'2026-11-01','2026-11-07') returning id",
            (facility,),
        ).fetchone()["id"]
        server.execute(
            "insert into leave_balances(facility_id,staff_id,period_id,leave_type,opening_balance) values(%s,%s,%s,'AL',20)",
            (facility, staff, period),
        )
        versions = []
        for kind in ("manual", "A", "B"):
            version = server.execute(
                "insert into roster_versions(facility_id,period_id,version_type) values(%s,%s,%s) returning id",
                (facility, period, kind),
            ).fetchone()["id"]
            shift = server.execute(
                "insert into shifts(facility_id,roster_version_id,date,shift_type,is_working,paid_minutes) values(%s,%s,'2026-11-02','A7',true,480) returning id",
                (facility, version),
            ).fetchone()["id"]
            assignment = server.execute(
                "insert into shift_assignments(facility_id,shift_id,staff_id,tasks) values(%s,%s,%s,array['medication']) returning id",
                (facility, shift, staff),
            ).fetchone()["id"]
            server.execute(
                "insert into shift_assignments(facility_id,shift_id,staff_id) values(%s,%s,%s)",
                (facility, shift, peer),
            )
            task = server.execute(
                "insert into task_assignments(facility_id,shift_assignment_id,staff_id,task_label,task_status) values(%s,%s,%s,'medication','done') returning id",
                (facility, assignment, staff),
            ).fetchone()["id"]
            server.execute(
                "insert into task_exceptions(facility_id,task_assignment_id,reported_by,reason_code) values(%s,%s,%s,'resident_refused')",
                (facility, task, staff),
            )
            versions.append(
                {"id": version, "shift": shift, "assignment": assignment, "task": task}
            )
        server.execute(
            "update roster_versions set status='published' where id=%s",
            (versions[1]["id"],),
        )
        yield {"facility": facility, "staff": staff, "peer": peer, "versions": versions}


def request(db, home, kind="AL", start="2026-11-02", end="2026-11-02"):
    return db.execute(
        "insert into leave_requests(facility_id,staff_id,category,leave_type,date_start,date_end) values(%s,%s,'al',%s,%s,%s) returning id",
        (home["facility"], home["staff"], kind, start, end),
    ).fetchone()["id"]


def test_approve_and_revoke_restore_both_rosters_and_exact_tasks(server, home):
    req = request(server, home, end="2026-11-03")
    server.execute("update leave_requests set status='approved' where id=%s", (req,))
    assert (
        server.execute(
            "select count(*) n from leave_roster_changes where request_id=%s", (req,)
        ).fetchone()["n"]
        == 4
    )
    for v in home["versions"][:2]:
        cell = server.execute(
            "select s.shift_type,a.tasks from shift_assignments a join shifts s on s.id=a.shift_id where a.id=%s",
            (v["assignment"],),
        ).fetchone()
        assert cell["shift_type"] == "AL"
        assert cell["tasks"] == []
        assert (
            server.execute(
                "select is_working from shifts s join shift_assignments a on a.shift_id=s.id where a.id=%s",
                (v["assignment"],),
            ).fetchone()["is_working"]
            is False
        )
        assert (
            server.execute(
                "select count(*) n from task_assignments where shift_assignment_id=%s and suspended_by_leave is null",
                (v["assignment"],),
            ).fetchone()["n"]
            == 0
        )
        assert (
            server.execute(
                "select count(*) n from task_exceptions where task_assignment_id=%s",
                (v["task"],),
            ).fetchone()["n"]
            == 1
        )
    assert (
        server.execute(
            "select count(*) n from shift_assignments a join shifts s on s.id=a.shift_id where a.staff_id=%s and s.shift_type='A7'",
            (home["peer"],),
        ).fetchone()["n"]
        == 3
    )
    server.execute("update leave_requests set status='approved' where id=%s", (req,))
    assert (
        server.execute(
            "select count(*) n from leave_roster_changes where request_id=%s", (req,)
        ).fetchone()["n"]
        == 4
    )
    server.execute(
        "update leave_requests set status='revoked',revoke_reason='Synthetic test' where id=%s",
        (req,),
    )
    for v in home["versions"]:
        cell = server.execute(
            "select * from shift_assignments where id=%s", (v["assignment"],)
        ).fetchone()
        assert cell["shift_id"] == v["shift"] and cell["tasks"] == ["medication"]
        assert (
            server.execute(
                "select task_status from task_assignments where id=%s", (v["task"],)
            ).fetchone()["task_status"]
            == "done"
        )
        assert (
            server.execute(
                "select count(*) n from task_exceptions where task_assignment_id=%s",
                (v["task"],),
            ).fetchone()["n"]
            == 1
        )
    assert (
        server.execute(
            "select count(*) n from shifts where facility_id=%s and date='2026-11-03'",
            (home["facility"],),
        ).fetchone()["n"]
        == 0
    )
    assert (
        server.execute(
            "select count(*) n from audit_logs where entity_id=%s and action='leave.roster.restore'",
            (req,),
        ).fetchone()["n"]
        == 4
    )


def test_invalid_code_and_overlap_roll_back_approval(server, home):
    bad = request(server, home, kind="UNKNOWN")
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="No organisation duty code"),
        server.transaction(),
    ):
        server.execute(
            "update leave_requests set status='approved' where id=%s", (bad,)
        )
    assert (
        server.execute(
            "select status from leave_requests where id=%s", (bad,)
        ).fetchone()["status"]
        == "pending"
    )
    first = request(server, home)
    second = request(server, home)
    server.execute("update leave_requests set status='approved' where id=%s", (first,))
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="Another approved"),
        server.transaction(),
    ):
        server.execute(
            "update leave_requests set status='approved' where id=%s", (second,)
        )
    assert (
        server.execute(
            "select status from leave_requests where id=%s", (second,)
        ).fetchone()["status"]
        == "pending"
    )


def test_foreign_event_staff_are_rejected_by_the_database(server, home):
    foreign = uuid4()
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="active members"),
        server.transaction(),
    ):
        server.execute(
            "insert into facility_events(facility_id,event_type,date,assigned_staff_ids) values(%s,'custom','2026-11-02',array[%s]::uuid[])",
            (home["facility"], foreign),
        )
    row = server.execute(
        "insert into facility_events(facility_id,event_type,date,assigned_staff_ids) values(%s,'custom','2026-11-02',array[%s]::uuid[]) returning assigned_staff_ids",
        (home["facility"], home["staff"]),
    ).fetchone()
    assert row["assigned_staff_ids"] == [home["staff"]]


def test_suspended_tasks_cannot_be_edited_and_the_guard_does_not_stay_open(
    server, home
):
    req = request(server, home)
    server.execute("update leave_requests set status='approved' where id=%s", (req,))
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="suspended"),
        server.transaction(),
    ):
        server.execute(
            "update task_assignments set task_status='pending' where id=%s",
            (home["versions"][0]["task"],),
        )
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="immutable"),
        server.transaction(),
    ):
        server.execute(
            "update shifts set shift_type='O' where id=%s",
            (home["versions"][1]["shift"],),
        )


def test_approval_and_revocation_reserve_and_release_the_exact_balance(server, home):
    req = request(server, home, end="2026-11-03")
    server.execute("update leave_requests set status='approved' where id=%s", (req,))
    balance = server.execute(
        "select used from leave_balances where staff_id=%s", (home["staff"],)
    ).fetchone()
    assert balance["used"] == 2
    server.execute(
        "update leave_requests set status='revoked',revoke_reason='Synthetic test' where id=%s",
        (req,),
    )
    assert (
        server.execute(
            "select used from leave_balances where staff_id=%s", (home["staff"],)
        ).fetchone()["used"]
        == 0
    )
