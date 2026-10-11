"""Fixture coverage for the final deterministic roster-publication gate.

These tests deliberately exercise no Supabase instance, migration, seed data or
credentials. The database publication RPC remains the production atomic
version/state lock; this suite verifies the API-side evidence policy passed to
that RPC.
"""
from __future__ import annotations

import pytest

from emma_core.services.publication import (
    PublishGateError,
    annotate_violations,
    require_publishable_validation,
)


def _validation(*violations: dict, **overrides: object) -> dict:
    result = {
        "passes": True,
        "hard_violation_count": 0,
        "soft_violation_count": sum(
            row.get("severity") == "soft" for row in violations
        ),
        "validation_run_id": "run-current",
        "input_digest": "a" * 64,
        "violations": list(violations),
    }
    result.update(overrides)
    return result


def _gate(validation: dict, omission_ids: list[str]):
    return require_publishable_validation(
        validation,
        omission_ids,
        expected_input_digest=validation["input_digest"],
    )


def _soft(**overrides: object) -> dict:
    row = {
        "rule_code": "night_chain",
        "severity": "soft",
        "staff_id": "staff-1",
        "date": "2026-10-11",
        "message": "A sleeping day is recommended after AN.",
        "details": {"required": ["SLEEP"], "actual": ["A"]},
        "resolved": False,
    }
    row.update(overrides)
    return row


def _hard(**overrides: object) -> dict:
    row = {
        "rule_code": "required_coverage",
        "severity": "hard",
        "date": "2026-10-11",
        "message": "Roster coverage is below the minimum.",
        "details": {"required": 2, "actual": 1},
        "resolved": False,
    }
    row.update(overrides)
    return row


def test_hard_violation_is_blocked_and_can_never_be_omitted():
    with pytest.raises(PublishGateError, match="hard or unknown") as exc:
        _gate(
            _validation(_hard(), passes=False, hard_violation_count=1),
            [],
        )
    assert exc.value.code == "hard_or_unknown_violation"


def test_soft_violation_is_blocked_until_its_current_server_id_is_ticked():
    with pytest.raises(PublishGateError, match="individually") as exc:
        _gate(_validation(_soft()), [])
    assert exc.value.code == "soft_violations_unacknowledged"


def test_all_current_soft_findings_can_be_acknowledged_then_published():
    source = _validation(_soft(), _soft(staff_id="staff-2", date="2026-10-12"))
    ids = [row["omission_id"] for row in annotate_violations(source["violations"])]

    findings, omitted = _gate(source, ids)

    assert [row["omission_id"] for row in omitted] == ids
    assert [row["omission_id"] for row in findings if row.get("omission_id")] == ids


def test_stale_or_new_issue_id_is_rejected_against_the_fresh_snapshot():
    old_id = annotate_violations([_soft(staff_id="staff-old")])[0]["omission_id"]
    with pytest.raises(PublishGateError, match="not in this fresh") as exc:
        _gate(_validation(_soft(staff_id="staff-new")), [old_id])
    assert exc.value.code == "invalid_soft_omission"


def test_unknown_severity_and_summary_mismatch_fail_closed():
    with pytest.raises(PublishGateError) as unknown:
        _gate(_validation(_soft(severity="warning")), [])
    assert unknown.value.code == "hard_or_unknown_violation"

    soft = _soft()
    soft_id = annotate_violations([soft])[0]["omission_id"]
    with pytest.raises(PublishGateError) as mismatch:
        _gate(
            _validation(soft, passes=False, hard_violation_count=0), [soft_id],
        )
    assert mismatch.value.code == "hard_or_unknown_violation"


def test_missing_persisted_validation_evidence_fails_closed():
    with pytest.raises(PublishGateError, match="persisted fresh") as exc:
        _gate(
            _validation(_soft(), validation_run_id=None),
            [],
        )
    assert exc.value.code == "validation_evidence_unavailable"


def test_reviewed_digest_must_match_the_new_server_snapshot():
    current = _validation(_soft())
    current_id = annotate_violations(current["violations"])[0]["omission_id"]

    with pytest.raises(PublishGateError) as exc:
        require_publishable_validation(
            current,
            [current_id],
            expected_input_digest="b" * 64,
        )

    assert exc.value.code == "stale_validation"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"violations": [_soft(resolved=True)]}, "validation_state_unknown"),
        ({"soft_violation_count": 0}, "validation_state_unknown"),
    ],
)
def test_resolved_or_summary_mismatched_findings_fail_closed(overrides, expected_code):
    source = _validation(_soft())
    source.update(overrides)
    ids = [row["omission_id"] for row in annotate_violations(source["violations"])]

    with pytest.raises(PublishGateError) as exc:
        _gate(source, ids)

    assert exc.value.code == expected_code
