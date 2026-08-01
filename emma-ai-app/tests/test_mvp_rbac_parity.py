"""Frontend/backend RBAC parity (spec 1.1).

The permission matrix is written twice - `emma_core/permissions.py` enforces it and
`src/lib/permissions.ts` hides menu items and guards routes with it. Two copies
drift, and the way that failure shows up in production is the worst kind: a menu
item the API refuses, or worse, a menu item the API allows because only one side
was tightened.

So the TypeScript table is parsed and compared cell by cell against the Python
one. The frontend intentionally carries a subset of features (it only gates what
the UI actually shows), so this checks the intersection - every feature the
frontend does declare must agree with the backend for all seven roles.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from emma_core.permissions import Feature, Grant, SystemRole, grant_for

TS_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "src" / "lib" / "permissions.ts"
)

# `'roster.view':  row('F', 'V', 'V', 'V', 'V', 'S', 'V'),`
ROW_RE = re.compile(
    r"^\s*'(?P<feature>[a-z_.]+)'\s*:\s*row\(\s*"
    r"(?P<grants>(?:'[FREVS-]'\s*,\s*){6}'[FREVS-]')\s*\)",
    re.MULTILINE,
)

# The column order declared by the `row()` helper's signature.
TS_COLUMNS = (
    SystemRole.OWNER,
    SystemRole.NURSE_MGR,
    SystemRole.ALLIED_HEALTH,
    SystemRole.ADMIN_CLERK,
    SystemRole.SCHEDULER,
    SystemRole.FRONTLINE,
    SystemRole.HR_AUDITOR,
)


def _parse_ts_matrix() -> dict[str, tuple[str, ...]]:
    text = TS_PATH.read_text(encoding="utf-8")
    rows = {
        m.group("feature"): tuple(re.findall(r"'([FREVS-])'", m.group("grants")))
        for m in ROW_RE.finditer(text)
    }
    assert rows, f"parsed no matrix rows from {TS_PATH} - has the format changed?"
    return rows


requires_frontend = pytest.mark.skipif(
    not TS_PATH.exists(),
    reason="frontend not present (backend is deployed without src/)",
)


@requires_frontend
def test_ts_row_order_matches_the_helper_signature():
    """Guards the parse itself: if `row(...)` is reordered, the comparison below
    would silently compare the wrong columns."""
    text = TS_PATH.read_text(encoding="utf-8")
    sig = re.search(r"const row = \(\s*(?P<params>[^)]*)\)", text)
    assert sig, "could not find the row() helper"
    names = re.findall(r"(\w+)\s*:\s*Grant", sig.group("params"))
    assert tuple(names) == tuple(c.value for c in TS_COLUMNS)


@requires_frontend
def test_frontend_features_are_real_backend_features():
    backend = {f.value for f in Feature}
    unknown = set(_parse_ts_matrix()) - backend
    assert not unknown, f"frontend declares features the backend does not: {unknown}"


@requires_frontend
def test_every_frontend_cell_matches_the_backend():
    mismatches = []
    for feature_value, grants in _parse_ts_matrix().items():
        feature = Feature(feature_value)
        for role, code in zip(TS_COLUMNS, grants, strict=True):
            expected = grant_for(role, feature)
            if expected is not Grant(code):
                mismatches.append(
                    f"{feature_value} x {role.value}: "
                    f"frontend={code!r} backend={expected.value!r}"
                )
    assert not mismatches, "frontend/backend RBAC drift:\n  " + "\n  ".join(mismatches)


@requires_frontend
def test_frontend_covers_every_route_gated_feature():
    """Anything the sidebar or route guard keys on must be in the frontend table,
    otherwise `grantFor` returns '-' and the menu item silently disappears for
    everyone - including OWNER."""
    nav = (TS_PATH.parent.parent / "components" / "layout" / "navRoutes.ts")
    if not nav.exists():
        pytest.skip("navRoutes.ts not present")
    declared = set(_parse_ts_matrix())
    used = set(re.findall(r"\]:\s*'([a-z_.]+)'", nav.read_text(encoding="utf-8")))
    missing = used - declared
    assert not missing, f"navRoutes maps routes to unknown features: {missing}"
