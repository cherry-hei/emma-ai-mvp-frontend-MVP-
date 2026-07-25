"""Staff directory reads. In the Phase 1 slice staff only appeared embedded in
the roster grid; the admin/personnel screens and the shift-editor dropdowns need
a standalone list."""
from __future__ import annotations


def list_staff(client, facility_id: str, *, search: str | None = None,
               rank: str | None = None) -> list[dict]:
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).order("created_at").execute().data)
    out: list[dict] = []
    needle = search.lower() if search else None
    for st in rows:
        if rank and st.get("rank") != rank:
            continue
        if needle:
            hay = f'{st.get("name") or ""} {st.get("name_en") or ""}'.lower()
            if needle not in hay:
                continue
        unit = st.get("unit") or {}
        out.append({**st, "unit_name": unit.get("name")})
    return out
