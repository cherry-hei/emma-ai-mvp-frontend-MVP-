"""Auth helpers: sign in and resolve the caller's facility + role."""
from __future__ import annotations

from supabase import create_client

from ..config import settings
from ..models import Profile
from ..care_workflows import CareWorkflowContext, resolve_care_workflow


def _naac_profile_configured(client, profile: Profile) -> bool:
    """Bounded read of the NAAC profile's critical active configuration.

    These are readiness checks, not guessed repairs. Rule dictionaries, workbook
    assets and real account/RLS acceptance still require Kien's release review.
    """
    try:
        cycles = (client.table("facility_json_configs").select("config_json")
                  .eq("facility_id", profile.facility_id)
                  .eq("config_key", "scheduling_cycle").eq("active", True).execute().data)
        if len(cycles) != 1 or cycles[0].get("config_json") != {
            "cycle_type": "42day", "days": 42, "weeks": 6,
        }:
            return False
        rows = (client.table("rule_definitions").select("rule_code,severity,config_json")
                .eq("facility_id", profile.facility_id).eq("active", True)
                .in_("rule_code", ["shift_sequence", "night_chain"]).execute().data)
        if len(rows) != 2 or {row.get("rule_code") for row in rows} != {"shift_sequence", "night_chain"}:
            return False
        if any(row.get("severity") != "hard" for row in rows):
            return False
        rules = {row["rule_code"]: row.get("config_json") or {} for row in rows}
        sequence, night = rules["shift_sequence"], rules["night_chain"]
        if (not 0 < sequence.get("max_consecutive_working_days", 0) <= 8
                or not sequence.get("forbidden_before") or not sequence.get("forbidden_after")
                or not sequence.get("no_consecutive")
                or "NO" not in night.get("sleep_codes", [])
                or "O" not in night.get("day_off_codes", [])):
            return False
        codes = (client.table("shift_definitions").select("shift_type")
                 .eq("org_id", profile.org_id)
                 .in_("shift_type", ["A7", "N10", "NO", "O"]).execute().data)
        return {row["shift_type"] for row in codes} == {"A7", "N10", "NO", "O"}
    except Exception:  # configuration unavailable must not grant generic B access
        return False


def sign_in(email: str, password: str):
    """Return (client, session); the client is bound to the user's token so RLS applies."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    client.postgrest.auth(res.session.access_token)
    return client, res.session


def refresh_session(refresh_token: str):
    """Exchange a refresh token for a fresh session (new access + refresh token).

    Powers POST /auth/refresh so the frontend can keep a session alive silently
    instead of forcing a re-login when the short-lived access token expires.
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = client.auth.refresh_session(refresh_token)
    client.postgrest.auth(res.session.access_token)
    return client, res.session


def get_profile(client, auth_user_id: str) -> Profile | None:
    # SQL: select p.*, jsonb_build_object('code', f.code, 'name', f.name) as facility,
    #             jsonb_build_object('id', o.id, 'code', o.code, 'name', o.name) as organisation
    #      from users_profile p
    #      left join facilities f on f.id = p.facility_id
    #      left join organisations o on o.id = p.org_id
    #      where p.auth_user_id = :auth_user_id
    #      limit 1
    rows = (client.table("users_profile")
            .select("*, facility:facilities(id,org_id,code,name,scheduling_cycle_days), organisation:organisations(id,code,name)")
            .eq("auth_user_id", auth_user_id).limit(2).execute().data)
    if len(rows) != 1:
        return None
    profile = Profile.model_validate({key: value for key, value in rows[0].items()
                                      if key != "care_workflow"})
    # A returned/calculated DB JSON field cannot supply its own authority.
    profile.care_workflow = resolve_care_workflow(profile, settings.care_workflow_bindings_json)
    if (profile.care_workflow.status == "ready"
            and profile.care_workflow.workflow == "NAAC"
            and not _naac_profile_configured(client, profile)):
        profile.care_workflow = CareWorkflowContext(
            status="invalid", org_id=profile.org_id, facility_id=profile.facility_id)
    return profile
