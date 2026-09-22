"""The charity a home belongs to, and the homes it runs.

Reads go through the caller's own client, so row level security answers the
question of which charity is theirs and nothing here has to filter by hand.
Provisioning is the exception: creating a charity is a setup act, it runs on the
service client from a script, and it is idempotent because it is run again every
time a home is added.
"""
from __future__ import annotations


_ORG_BY_FACILITY: dict[str, str] = {}


def org_id_for(client, facility_id: str) -> str:
    """The charity that owns a home.

    Cached for the life of the process because a home does not change charity,
    and the dictionaries are read on nearly every roster call: without the cache
    each of those pays a second round trip to learn something that never moves.
    """
    if not facility_id:
        raise ValueError("a facility is needed to resolve its organisation")
    cached = _ORG_BY_FACILITY.get(facility_id)
    if cached:
        return cached
    # SQL: select org_id from facilities where id = :facility_id
    rows = (client.table("facilities").select("org_id")
            .eq("id", facility_id).execute().data)
    org_id = rows[0].get("org_id") if rows else None
    if not org_id:
        raise ValueError(f"facility {facility_id} belongs to no organisation")
    _ORG_BY_FACILITY[facility_id] = org_id
    return org_id


def current(client) -> dict | None:
    """The caller's charity. Returns None for an account not yet attached to one."""
    # SQL: select id, code, name, created_at from organisations
    #      -- + RLS: where id = public.current_org_id()
    rows = (client.table("organisations")
            .select("id,code,name,created_at").limit(1).execute().data)
    return rows[0] if rows else None


def homes(client) -> list[dict]:
    """Every home in the caller's charity, which for one home is a list of one."""
    # SQL: select id, code, name, type, timezone, scheduling_cycle_days, capacity
    #      from facilities order by code
    #      -- + RLS: where org_id = public.current_org_id()
    return (client.table("facilities")
            .select("id,code,name,type,timezone,scheduling_cycle_days,capacity")
            .order("code").execute().data)


def provision(service_client, code: str, name: str) -> dict:
    """Create the charity if it is not there yet, and return it either way.

    Takes the service client on purpose. A signed-in user can only ever see their
    own charity, so creating a new one is not something the API can do, and it
    should not be: a new charity is an onboarding decision, not a request.
    """
    code = code.strip()
    if not code:
        raise ValueError("an organisation needs a code")
    # SQL: select id, code, name from organisations where code = :code
    rows = (service_client.table("organisations")
            .select("id,code,name").eq("code", code).execute().data)
    if rows:
        return rows[0]
    # SQL: insert into organisations (code, name) values (:code, :name) returning *
    return (service_client.table("organisations")
            .insert({"code": code, "name": name})
            .execute().data[0])
