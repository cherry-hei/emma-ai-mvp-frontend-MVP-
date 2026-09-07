"""The Emergency SL closed loop against a real database, end to end.

tests/test_replacement_offers.py proves the algebra with fake clients: who may
answer, what an approval delegates to, which statuses are terminal. None of that
touches a migration, a check constraint, an RLS policy or the candidate engine
reading real rest and hour history, so all of it can pass while the loop is
broken in the environment a manager actually uses.

This walks the whole thing on Care Home B, the demo home, in the order the UAT
script does it:

    incident -> candidates -> offers -> one accepts, one declines
             -> manager approves -> the losing offers close
             -> the roster moves -> the audit records it

and then puts everything back. Skips cleanly when the database is unreachable,
or when the demo home has no roster with two eligible cover candidates - that is
a seeding problem to report, not a failure to hide.
"""
from __future__ import annotations

import pytest

from emma_core.services import replacement_offers as offers

FACILITY_CODE = "B"


@pytest.fixture(scope="module")
def sb():
    try:
        from emma_core.db import get_service_client
        client = get_service_client()
        client.table("facilities").select("id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 - no database, nothing to say
        pytest.skip(f"Supabase not reachable: {exc}")
    return client


@pytest.fixture(scope="module")
def facility_id(sb) -> str:
    rows = (sb.table("facilities").select("id,code")
            .eq("code", FACILITY_CODE).execute().data)
    if not rows:
        pytest.skip(f"no facility with code {FACILITY_CODE!r}")
    return rows[0]["id"]


@pytest.fixture(scope="module")
def staffed_shift(sb, facility_id) -> dict:
    """The most recent shift on the demo home that somebody is rostered on.

    Deliberately "most recent" rather than "today": the demo roster is seeded in
    blocks and is usually not current, and a test that hard-codes today's date
    reports a seeding gap as a product failure.
    """
    shifts = (sb.table("shifts").select("id,date,shift_type")
              .eq("facility_id", facility_id).order("date", desc=True)
              .limit(200).execute().data)
    for shift in shifts:
        rows = (sb.table("shift_assignments").select("id,staff_id,tasks")
                .eq("shift_id", shift["id"]).execute().data)
        if rows:
            return {**shift, "assignment": rows[0]}
    pytest.skip("the demo home has no rostered shift to build an incident on")


@pytest.fixture
def incident(sb, facility_id, staffed_shift):
    """An open SL incident on that shift, removed again afterwards."""
    from emma_core.services import incidents as inc_svc

    row = inc_svc.open_incident(
        sb, facility_id,
        staff_id=staffed_shift["assignment"]["staff_id"],
        incident_type="SL", on_date=str(staffed_shift["date"]),
        reason="integration test", shift_id=staffed_shift["id"])
    yield row
    _cleanup(sb, facility_id, row["id"], staffed_shift)


def _cleanup(sb, facility_id: str, incident_id: str, shift: dict) -> None:
    """Put the roster back. Best effort - a failed teardown must not mask a
    failed assertion, so nothing in here raises."""
    for table, column in (("replacement_offers", "incident_id"),
                          ("sl_incidents", "id")):
        try:
            sb.table(table).delete().eq("facility_id", facility_id) \
                .eq(column, incident_id).execute()
        except Exception:  # noqa: BLE001
            pass
    try:
        original = shift["assignment"]
        sb.table("shift_assignments").update({
            "staff_id": original["staff_id"], "status": "scheduled",
            "source_incident_id": None, "incident_assignment_kind": None,
        }).eq("id", original["id"]).execute()
    except Exception:  # noqa: BLE001
        pass


def _eligible(sb, facility_id: str, incident: dict) -> list[str]:
    from emma_core.services import incidents as inc_svc

    return [c["candidate_staff_id"]
            for c in inc_svc.build_candidates(sb, facility_id, incident)
            if c["compliance_ok"]]


def test_the_whole_loop_runs_on_real_rows(sb, facility_id, incident, staffed_shift):
    eligible = _eligible(sb, facility_id, incident)
    if len(eligible) < 2:
        pytest.skip(
            f"the demo home offers {len(eligible)} compliant cover candidate(s) for "
            f"{staffed_shift['date']}; two are needed to test accept against decline")

    accepts, declines = eligible[0], eligible[1]

    made = offers.offer(sb, facility_id, incident["id"],
                        staff_ids=[accepts, declines], note="integration test")
    assert len(made) == 2
    assert {row["status"] for row in made} == {"pending"}
    by_staff = {row["offered_staff_id"]: row for row in made}

    # The two answers a real UAT gives.
    accepted = offers.respond(sb, facility_id, by_staff[accepts]["id"],
                              staff_id=accepts, accept=True)
    declined = offers.respond(sb, facility_id, by_staff[declines]["id"],
                              staff_id=declines, accept=False)
    assert accepted["status"] == "accepted"
    assert declined["status"] == "declined"

    # Accepting is not being rostered - the shift must still belong to the
    # absent person until a manager commits it. This is the rule the PWA has to
    # respect, so it is worth failing loudly on.
    still = (sb.table("shift_assignments").select("staff_id")
             .eq("id", staffed_shift["assignment"]["id"]).execute().data[0])
    assert still["staff_id"] == staffed_shift["assignment"]["staff_id"], \
        "accepting an offer moved the roster before any manager approved it"

    result = offers.approve(sb, facility_id, by_staff[accepts]["id"])
    assert result["offer"]["status"] == "approved"
    assert result["offer"]["approved_at"]


def test_approval_closes_the_offers_nobody_won(sb, facility_id, incident,
                                               staffed_shift):
    eligible = _eligible(sb, facility_id, incident)
    if len(eligible) < 3:
        pytest.skip("three compliant candidates are needed to test superseding")

    winner, loser, undecided = eligible[0], eligible[1], eligible[2]
    made = {row["offered_staff_id"]: row for row in offers.offer(
        sb, facility_id, incident["id"], staff_ids=[winner, loser, undecided])}

    offers.respond(sb, facility_id, made[winner]["id"], staff_id=winner, accept=True)
    offers.respond(sb, facility_id, made[loser]["id"], staff_id=loser, accept=False)
    # `undecided` never answers, which is the case that used to leave someone
    # waiting on a shift that had already been covered.
    offers.approve(sb, facility_id, made[winner]["id"])

    after = {row["offered_staff_id"]: row["status"] for row in
             offers.list_offers(sb, facility_id, incident_id=incident["id"])}
    assert after[winner] == "approved"
    assert after[loser] == "declined", "a decline must not be rewritten by the approval"
    assert after[undecided] == "superseded"


def test_approval_moves_the_roster_and_records_why(sb, facility_id, incident,
                                                   staffed_shift):
    eligible = _eligible(sb, facility_id, incident)
    if not eligible:
        pytest.skip("no compliant cover candidate on the demo home")

    cover = eligible[0]
    made = offers.offer(sb, facility_id, incident["id"], staff_ids=[cover])[0]
    offers.respond(sb, facility_id, made["id"], staff_id=cover, accept=True)
    offers.approve(sb, facility_id, made["id"])

    moved = (sb.table("shift_assignments").select("staff_id,source_incident_id")
             .eq("id", staffed_shift["assignment"]["id"]).execute().data)
    covered = (sb.table("shift_assignments").select("staff_id,source_incident_id")
               .eq("shift_id", staffed_shift["id"])
               .eq("staff_id", cover).execute().data)
    assert covered or (moved and moved[0]["staff_id"] == cover), \
        "the shift is still not covered by the person the manager approved"

    trail = (sb.table("audit_logs").select("action,entity_id,after_json")
             .eq("facility_id", facility_id)
             .eq("entity_table", "replacement_offers")
             .eq("entity_id", made["id"]).execute().data)
    assert trail, "an approval that changes the roster left no audit row"
    assert any((row.get("after_json") or {}).get("replacement_staff_id") == cover
               for row in trail), "the audit row does not say who was put on the shift"
