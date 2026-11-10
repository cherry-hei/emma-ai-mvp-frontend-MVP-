"""Explicit Care Home A/SA and B/NAAC authority, independent of display names.

Bindings are an operator-reviewed, server-only deployment setting. Existing demo
facility B is NOT automatically NAAC. A missing/mismatched binding grants nothing.
This does not provision, rename, move or merge an organisation, home or account.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .permissions import Feature, Grant, SystemRole, grant_for, normalise_role


class WorkflowActions(BaseModel):
    roster_edit: bool = False
    roster_delete: bool = False
    roster_generate: bool = False
    roster_batch: bool = False
    roster_publish: bool = False
    leave_recommend: bool = False
    leave_decide: bool = False
    staff_manage: bool = False
    rules_manage: bool = False


class RoleLabel(BaseModel):
    en: str = "Workflow not configured"
    zh: str = "流程尚未設定"


class CareWorkflowContext(BaseModel):
    status: Literal["ready", "unbound", "invalid"] = "unbound"
    care_home: Literal["A", "B"] | None = None
    workflow: Literal["SA", "NAAC"] | None = None
    role: str | None = None
    role_label: RoleLabel = Field(default_factory=RoleLabel)
    org_id: str | None = None
    facility_id: str | None = None
    unit_ids: list[str] = Field(default_factory=list)
    permissions: dict[str, Grant] = Field(
        default_factory=lambda: {feature.value: Grant.NONE for feature in Feature})
    actions: WorkflowActions = Field(default_factory=WorkflowActions)
    roster_scope: Literal["facility", "self_and_units", "self", "none"] = "none"


class WorkflowMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: UUID
    auth_user_id: UUID
    expected_system_role: SystemRole
    workflow_role: str
    staff_id: UUID | None = None
    unit_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_units(self):
        if len(self.unit_ids) != len(set(self.unit_ids)):
            raise ValueError("Unit membership IDs must be unique")
        return self


_NAAC_BASE_ROLES = {
    "director": SystemRole.OWNER,
    "deputy": SystemRole.OWNER,
    "nurse": SystemRole.NURSE_MGR,
    "staff": SystemRole.FRONTLINE,
}


class CareWorkflowBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    care_home: Literal["A", "B"]
    workflow: Literal["SA", "NAAC"]
    org_id: UUID
    facility_id: UUID
    memberships: list[WorkflowMembership] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_appointments(self):
        if {"A": "SA", "B": "NAAC"}[self.care_home] != self.workflow:
            raise ValueError("Care Home A uses SA; Care Home B uses NAAC")
        if len({m.profile_id for m in self.memberships}) != len(self.memberships):
            raise ValueError("Duplicate profile appointment")
        if len({m.auth_user_id for m in self.memberships}) != len(self.memberships):
            raise ValueError("Duplicate auth-user appointment")
        for member in self.memberships:
            if self.workflow == "SA":
                if member.workflow_role != member.expected_system_role.value:
                    raise ValueError("SA appointment must use its canonical system role")
            elif _NAAC_BASE_ROLES.get(member.workflow_role) != member.expected_system_role:
                raise ValueError("NAAC appointment does not match its required base role")
            if member.expected_system_role == SystemRole.FRONTLINE and not member.staff_id:
                raise ValueError("A staff appointment requires its exact staff record")
            if self.workflow == "NAAC" and member.workflow_role == "nurse" and not member.unit_ids:
                raise ValueError("A nurse appointment requires explicit unit membership")
            if self.workflow == "NAAC" and member.workflow_role == "nurse" and not member.staff_id:
                raise ValueError("A nurse appointment requires its exact staff record")
        return self


class CareWorkflowBindings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    bindings: list[CareWorkflowBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def separate_tenants(self):
        for field in ("care_home", "org_id", "facility_id"):
            if len({getattr(b, field) for b in self.bindings}) != len(self.bindings):
                raise ValueError("A and B must have distinct reviewed tenant bindings")
        all_profiles = [m.profile_id for b in self.bindings for m in b.memberships]
        if len(all_profiles) != len(set(all_profiles)):
            raise ValueError("A profile cannot be appointed to two homes")
        all_users = [m.auth_user_id for b in self.bindings for m in b.memberships]
        if len(all_users) != len(set(all_users)):
            raise ValueError("A and B require separate login identities until membership selection exists")
        return self


_LABELS = {
    "director": ("Director", "主任"),
    "deputy": ("Appointed deputy", "獲委任副主任"),
    "nurse": ("Nurse", "護士"),
    "staff": ("Staff", "員工"),
    "OWNER": ("Superintendent / appointed deputy", "院長／獲委任副院長"),
    "NURSE_MGR": ("Nursing Officer", "護理主任"),
    "ALLIED_HEALTH": ("Allied Health", "治療師"),
    "ADMIN_CLERK": ("Admin Clerk", "文員"),
    "SCHEDULER": ("Scheduler", "排更員"),
    "FRONTLINE": ("Staff", "員工"),
    "HR_AUDITOR": ("HR / Audit", "人事及審計"),
}


def _naac_permissions(role: str) -> dict[str, Grant]:
    """The approved minimum NAAC workflow; unstated features remain closed.

    The deputy is explicitly appointed and has no final decision authority.
    Nurse manual cell editing is an action, never AI generation/batch permission.
    """
    p = {f.value: Grant.NONE for f in Feature}
    if role in ("director", "deputy"):
        for feature in (
            Feature.DASHBOARD, Feature.ROSTER_VIEW, Feature.REPORTS,
            Feature.AUDIT_LOG, Feature.STAFF_PORTFOLIO, Feature.STAFF_PROFILE_WRITE,
            Feature.FACILITY_SETTINGS, Feature.ROSTER_RULE_ENGINE,
            Feature.TASK_CODES, Feature.WORKING_HOURS, Feature.DUAL_HOURS_REGIME,
        ):
            p[feature.value] = Grant.FULL if role == "director" else Grant.EDIT
        p[Feature.AUDIT_LOG.value] = Grant.VIEW
        p[Feature.REPORTS.value] = Grant.FULL if role == "director" else Grant.VIEW
        p[Feature.ROSTER_AI_DRAFT.value] = Grant.FULL if role == "director" else Grant.EDIT
        for feature in (Feature.APPROVE_LEAVE, Feature.APPROVE_DUTY_DO, Feature.APPROVE_SICK):
            p[feature.value] = Grant.FULL if role == "director" else Grant.RECOMMEND
        if role == "director":
            p[Feature.ROSTER_PUBLISH.value] = Grant.FULL
    elif role == "nurse":
        p[Feature.ROSTER_VIEW.value] = Grant.VIEW
        # Nurses remain employees for their own requests/profile; these SELF
        # grants do not grant preliminary or final approval of anyone else.
        for feature in (Feature.APPROVE_LEAVE, Feature.APPROVE_DUTY_DO,
                        Feature.APPROVE_SICK, Feature.STAFF_PORTFOLIO,
                        Feature.CERTIFICATES, Feature.ALERTS):
            p[feature.value] = Grant.SELF
    elif role == "staff":
        for feature in (
            Feature.ROSTER_VIEW, Feature.STAFF_PORTFOLIO, Feature.CERTIFICATES,
            Feature.APPROVE_LEAVE, Feature.APPROVE_DUTY_DO, Feature.APPROVE_SICK,
            Feature.ALERTS, Feature.TASK_CODES,
        ):
            p[feature.value] = Grant.SELF
    return p


def resolve_care_workflow(profile: Any, raw_bindings: str) -> CareWorkflowContext:
    """Resolve only verified server profile IDs against explicit appointments.

    No matching by facility name/code, email, URL, rank, or job-title inference.
    Invalid config, role drift and inconsistent organisation membership deny.
    """
    empty = dict(org_id=profile.org_id, facility_id=profile.facility_id)
    if not raw_bindings.strip():
        return CareWorkflowContext(**empty)
    try:
        config = CareWorkflowBindings.model_validate_json(raw_bindings)
    except (ValidationError, ValueError):
        return CareWorkflowContext(status="invalid", **empty)
    binding = next((b for b in config.bindings if str(b.facility_id) == profile.facility_id), None)
    if binding is None:
        return CareWorkflowContext(**empty)
    facility = profile.facility
    if (
        str(binding.org_id) != profile.org_id
        or not facility
        or facility.id != profile.facility_id
        or facility.org_id != profile.org_id
        or (profile.organisation and profile.organisation.id != profile.org_id)
        # These are consistency checks AFTER identity matching, never identity
        # inference. Generic demo B/31 days is not NAAC's operational profile.
        or facility.code != ("A" if binding.workflow == "SA" else "NAAC")
        or facility.scheduling_cycle_days != (28 if binding.workflow == "SA" else 42)
    ):
        return CareWorkflowContext(status="invalid", **empty)
    member = next((m for m in binding.memberships
                   if str(m.profile_id) == profile.id
                   and str(m.auth_user_id) == profile.auth_user_id), None)
    if member is None:
        return CareWorkflowContext(**empty)
    if normalise_role(profile.role) != member.expected_system_role:
        return CareWorkflowContext(status="invalid", **empty)
    if member.staff_id and str(member.staff_id) != profile.staff_id:
        return CareWorkflowContext(status="invalid", **empty)
    if binding.workflow == "SA":
        permissions = {f.value: grant_for(profile.role, f) for f in Feature}
        edit = permissions[Feature.ROSTER_AI_DRAFT.value] in (Grant.FULL, Grant.EDIT)
        actions = WorkflowActions(
            roster_edit=edit, roster_delete=edit, roster_generate=edit, roster_batch=edit,
            roster_publish=permissions[Feature.ROSTER_PUBLISH.value] == Grant.FULL,
            leave_recommend=permissions[Feature.APPROVE_LEAVE.value] in (Grant.FULL, Grant.RECOMMEND),
            leave_decide=permissions[Feature.APPROVE_LEAVE.value] == Grant.FULL,
            staff_manage=permissions[Feature.STAFF_PROFILE_WRITE.value] in (Grant.FULL, Grant.EDIT),
            rules_manage=permissions[Feature.FACILITY_SETTINGS.value] in (Grant.FULL, Grant.EDIT),
        )
        scope = "self" if member.expected_system_role == SystemRole.FRONTLINE else "facility"
    else:
        permissions = _naac_permissions(member.workflow_role)
        management = member.workflow_role in ("director", "deputy")
        final = member.workflow_role == "director"
        actions = WorkflowActions(
            roster_edit=management or member.workflow_role == "nurse",
            roster_delete=management,
            roster_generate=management, roster_batch=management, roster_publish=final,
            leave_recommend=management, leave_decide=final,
            staff_manage=management, rules_manage=management,
        )
        scope = "facility" if management else "self_and_units"
    label = _LABELS[member.workflow_role]
    return CareWorkflowContext(
        status="ready", care_home=binding.care_home, workflow=binding.workflow,
        role=member.workflow_role, role_label=RoleLabel(en=label[0], zh=label[1]),
        org_id=profile.org_id, facility_id=profile.facility_id,
        unit_ids=[str(unit) for unit in member.unit_ids], permissions=permissions,
        actions=actions, roster_scope=scope,
    )
