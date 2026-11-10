"""Explicit synthetic SA appointments for existing offline guard regressions."""
import json
from uuid import NAMESPACE_URL, uuid5

from emma_core.care_workflows import resolve_care_workflow
from emma_core.models import Profile
from emma_core.permissions import SystemRole, normalise_role


def sa_profile(role: str, *, staff_id: str | None = None) -> Profile:
    def synthetic_id(label: str) -> str:
        return str(uuid5(NAMESPACE_URL, "https://offline.invalid/emma/" + label))

    canonical = normalise_role(role)
    assert canonical is not None
    if staff_id is None and canonical == SystemRole.FRONTLINE:
        staff_id = "staff-fixture"
    profile = Profile(
        id=synthetic_id("profile"), auth_user_id=synthetic_id("auth"),
        org_id=synthetic_id("org"), facility_id=synthetic_id("facility"),
        role=role, staff_id=synthetic_id(staff_id) if staff_id else None,
        facility={"id": synthetic_id("facility"), "org_id": synthetic_id("org"),
                  "code": "A", "name": "Offline fixture", "scheduling_cycle_days": 28},
        organisation={"id": synthetic_id("org")},
    )
    bindings = {"schema_version": 1, "bindings": [{
        "care_home": "A", "workflow": "SA", "org_id": profile.org_id,
        "facility_id": profile.facility_id, "memberships": [{
            "profile_id": profile.id, "auth_user_id": profile.auth_user_id,
            "expected_system_role": canonical.value, "workflow_role": canonical.value,
            "staff_id": profile.staff_id, "unit_ids": [],
        }],
    }]}
    profile.care_workflow = resolve_care_workflow(profile, json.dumps(bindings))
    assert profile.care_workflow.status == "ready"
    return profile
