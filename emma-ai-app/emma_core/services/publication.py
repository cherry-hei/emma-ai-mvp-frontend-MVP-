"""Authoritative roster-publication gate.

The browser may *display* validation findings and collect a superintendent's
soft-policy acknowledgements, but this module decides whether the requested
acknowledgements are complete for a fresh deterministic run.  It deliberately
uses stable finding fingerprints rather than database row IDs: the caller
cannot acknowledge a previous/stale validation run by guessing an ID.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping


class PublishGateError(ValueError):
    """A safe, machine-readable refusal from the publication gate."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _normalise(value: Any) -> Any:
    """Make finding evidence deterministic before it enters a fingerprint."""
    if isinstance(value, Mapping):
        return {str(key): _normalise(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    return str(value) if value is not None and not isinstance(value, (str, int, float, bool)) else value


def _base_omission_id(violation: Mapping[str, Any]) -> str:
    """Fingerprint all evidence that identifies one deterministic finding."""
    evidence = {
        "rule_code": violation.get("rule_code"),
        "severity": str(violation.get("severity") or "").strip().lower(),
        "shift_id": violation.get("shift_id"),
        "staff_id": violation.get("staff_id"),
        "date": violation.get("date"),
        "unit_id": violation.get("unit_id"),
        "task_assignment_id": violation.get("task_assignment_id"),
        "event_id": violation.get("event_id"),
        "rule_definition_id": violation.get("rule_definition_id"),
        "message": violation.get("message"),
        "details": violation.get("details") or {},
    }
    encoded = json.dumps(_normalise(evidence), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"soft-{sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


def annotate_violations(violations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Copy findings and add an omission ID to each *soft* finding only.

    The suffix keeps IDs unique even if an engine happens to emit two otherwise
    identical findings. Validation sorts findings before this function is called,
    so those suffixes are reproducible for the same snapshot.
    """
    copied = [deepcopy(dict(row)) for row in violations]
    bases = [
        _base_omission_id(row)
        for row in copied
        if str(row.get("severity") or "").strip().lower() == "soft"
    ]
    totals = Counter(bases)
    seen: Counter[str] = Counter()
    for row in copied:
        if str(row.get("severity") or "").strip().lower() != "soft":
            continue
        base = _base_omission_id(row)
        seen[base] += 1
        row["omission_id"] = base if totals[base] == 1 else f"{base}-{seen[base]}"
    return copied


def _is_zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def require_publishable_validation(
    validation: Mapping[str, Any],
    requested_soft_omission_ids: Iterable[str],
    *,
    expected_input_digest: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return annotated findings and approved soft omissions or fail closed.

    `validation` must be the just-computed server deterministic result.  Hard,
    malformed, unknown-severity, missing-evidence, and stale/incomplete states
    are all denials; a client cannot turn any of them into a soft omission.
    """
    run_id = validation.get("validation_run_id")
    digest = validation.get("input_digest")
    if not isinstance(run_id, str) or not run_id or not isinstance(digest, str) or not digest:
        raise PublishGateError(
            "validation_evidence_unavailable",
            "Publication requires a persisted fresh deterministic validation run.",
        )
    # A checkbox is an acknowledgement of the snapshot the owner actually saw.
    # The API has already recomputed `validation`; this client-held digest merely
    # detects a changed snapshot between review and publish. It can never supply
    # a pass/fail result or bypass the server's deterministic evidence.
    if not isinstance(expected_input_digest, str) or expected_input_digest != digest:
        raise PublishGateError(
            "stale_validation",
            "The roster or its rules changed after review; run the checks again and acknowledge the current findings.",
        )
    raw = validation.get("violations")
    if not isinstance(raw, list):
        raise PublishGateError("validation_state_unknown", "Deterministic validation returned an unknown finding state.")
    # `validate_roster()` returns one new, unresolved row for every current
    # finding. A resolved (or missing) state here would mean callers are trying
    # to mix historical evidence into an acknowledgement decision; fail closed
    # rather than silently treating it as a harmless warning.
    if any(
        not isinstance(row, Mapping) or row.get("resolved") is not False
        for row in raw
    ):
        raise PublishGateError(
            "validation_state_unknown",
            "Publication requires a complete unresolved finding list from the fresh validation run.",
        )
    findings = annotate_violations(raw)
    requested = list(requested_soft_omission_ids)
    if any(not isinstance(item, str) or not item for item in requested) or len(set(requested)) != len(requested):
        raise PublishGateError("invalid_soft_omission", "Soft omissions must be a unique list of current finding IDs.")

    hard_or_unknown = [
        row for row in findings
        if str(row.get("severity") or "").strip().lower() != "soft"
    ]
    all_ids = {str(row["omission_id"]) for row in findings if row.get("omission_id")}
    submitted_known_non_soft = set(requested) & {
        # There must never be a soft-omission ID for a hard finding. Keep this
        # branch defensive for future schema changes or a compromised client.
        str(row.get("omission_id")) for row in hard_or_unknown if row.get("omission_id")
    }
    if submitted_known_non_soft:
        raise PublishGateError("hard_violation_cannot_omit", "Hard or unknown-severity findings cannot be omitted.")
    unknown_requested = set(requested) - all_ids
    if unknown_requested:
        raise PublishGateError("invalid_soft_omission", "A requested soft omission is not in this fresh validation run.")

    hard_rows = sum(
        str(row.get("severity") or "").strip().lower() == "hard"
        for row in findings
    )
    soft_rows = len(soft := [row for row in findings if row.get("omission_id")])
    hard_count = validation.get("hard_violation_count")
    soft_count = validation.get("soft_violation_count")
    # Never treat an evidence-summary mismatch as a benign soft warning. These
    # counts are persisted with the run and must account for every current row.
    # Unknown severities are already classified as blockers above.
    if (
        not _is_nonnegative_int(hard_count)
        or not _is_nonnegative_int(soft_count)
        or hard_count != hard_rows
        or soft_count != soft_rows
    ):
        raise PublishGateError(
            "validation_state_unknown",
            "Deterministic validation summary does not match its finding evidence.",
        )
    if validation.get("passes") is not True or not _is_zero_int(hard_count):
        raise PublishGateError("hard_or_unknown_violation", "Publication is blocked by hard or unknown validation state.")
    if hard_or_unknown:
        raise PublishGateError("hard_or_unknown_violation", "Publication is blocked by hard or unknown-severity findings.")

    required = {str(row["omission_id"]) for row in soft}
    missing = required - set(requested)
    if missing:
        raise PublishGateError(
            "soft_violations_unacknowledged",
            "Every soft violation from this fresh validation run must be individually acknowledged before publication.",
        )
    return findings, soft


def resolve_persisted_soft_omission_row_ids(
    client: Any,
    *,
    facility_id: str,
    roster_version_id: str,
    validation_run_id: str,
    approved_soft_omission_ids: Iterable[str],
) -> list[str]:
    """Map reviewed stable IDs to the exact persisted violation rows.

    A browser only ever supplies deterministic omission fingerprints.  The
    service re-derives those fingerprints from the just-persisted validation
    evidence and passes *database* row IDs to the publication RPC.  This keeps
    a guessed historical/cross-tenant violation ID out of the client contract.
    """
    approved = list(approved_soft_omission_ids)
    if any(not isinstance(x, str) or not x for x in approved) or len(set(approved)) != len(approved):
        raise PublishGateError("invalid_soft_omission", "Soft evidence IDs must be unique.")
    rows = (
        client.table("violation_log")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("roster_version_id", roster_version_id)
        .eq("validation_run_id", validation_run_id)
        .eq("severity", "soft")
        .eq("resolved", False)
        .execute()
        .data
        or []
    )
    by_omission_id: dict[str, str] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or not row.get("id")
            or not isinstance(row.get("omission_id"), str)
            or not row["omission_id"]
        ):
            raise PublishGateError(
                "validation_evidence_unavailable",
                "Publication requires persisted soft-finding evidence.",
            )
        omission_id = str(row["omission_id"])
        if omission_id in by_omission_id:
            raise PublishGateError(
                "validation_evidence_unavailable",
                "Persisted soft findings contain a duplicate omission identifier.",
            )
        by_omission_id[omission_id] = str(row["id"])
    if set(approved) != set(by_omission_id):
        raise PublishGateError(
            "validation_evidence_unavailable",
            "Persisted soft findings do not exactly match the reviewed validation snapshot.",
        )
    return [by_omission_id[omission_id] for omission_id in approved]
