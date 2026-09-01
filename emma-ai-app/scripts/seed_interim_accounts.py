"""Interim login accounts on Care Home B, so the staff PWA has something to sign in as.

    python scripts/seed_interim_accounts.py

These are demo logins on a demo home. They give the frontend a token and a
spread of ranks and nothing else, so they must never stand in for a real home in
an acceptance test. Idempotent: an account that already exists is reused, and
its password is reset to the shared dev one.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# The home names are Chinese and a Windows console is not UTF-8 by default.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from emma_core.db import get_service_client  # noqa: E402

FACILITY_CODE = "B"
PASSWORD = "EmmaDev123!"

MANAGER = ("manager.b@emma.local", "superintendent")

# One of each rank the roster actually distinguishes, so the app can be driven
# through a rank-gated screen without inventing a staff row by hand.
STAFF = [
    ("staff.rn.b@emma.local", "示範護士", "Demo RN", "RN", "local_ft", 44),
    ("staff.hw.b@emma.local", "示範保健員", "Demo HW", "HW", "local_ft", 44),
    ("staff.pcw.b@emma.local", "示範護理員", "Demo PCW", "PCW", "local_pt", 24),
]

sb = get_service_client()


def facility() -> dict:
    rows = sb.table("facilities").select("id,code,name").eq("code", FACILITY_CODE) \
        .execute().data
    if not rows:
        raise SystemExit(f"no facility with code {FACILITY_CODE!r}; run scripts/seed.py first")
    return rows[0]


def auth_user(email: str) -> str:
    """Create the auth user, or reuse and reset the one already there."""
    for user in sb.auth.admin.list_users():
        if (user.email or "").lower() == email.lower():
            sb.auth.admin.update_user_by_id(user.id, {"password": PASSWORD})
            return user.id
    return sb.auth.admin.create_user({
        "email": email, "password": PASSWORD, "email_confirm": True}).user.id


def staff_row(facility_id: str, name: str, name_en: str, rank: str,
              employment: str, hours: int) -> str:
    rows = sb.table("staff").select("id").eq("facility_id", facility_id) \
        .eq("name_en", name_en).execute().data
    if rows:
        return rows[0]["id"]
    staff_id = sb.table("staff").insert({
        "facility_id": facility_id, "name": name, "name_en": name_en,
        "rank": rank, "employment_type": employment, "contracted_hours": hours,
        "is_audited_for_medication": rank in ("RN", "EN"), "status": "active",
    }).execute().data[0]["id"]
    sb.table("staff_contracts").insert({
        "facility_id": facility_id, "staff_id": staff_id,
        "weekly_hours": hours, "max_weekly_hours": hours + 8,
    }).execute()
    return staff_id


def profile(auth_id: str, facility_id: str, email: str, role: str,
            staff_id: str | None) -> None:
    row = {"auth_user_id": auth_id, "facility_id": facility_id, "email": email,
           "role": role, "staff_id": staff_id}
    existing = sb.table("users_profile").select("id").eq("auth_user_id", auth_id) \
        .execute().data
    if existing:
        sb.table("users_profile").update(row).eq("id", existing[0]["id"]).execute()
    else:
        sb.table("users_profile").insert(row).execute()


def main() -> None:
    home = facility()
    print(f"Interim accounts on {home['name']} ({home['code']}). Demo home, not NAAC.")

    email, role = MANAGER
    profile(auth_user(email), home["id"], email, role, None)
    print(f"  {email:<26} {role}")

    for email, name, name_en, rank, employment, hours in STAFF:
        staff_id = staff_row(home["id"], name, name_en, rank, employment, hours)
        profile(auth_user(email), home["id"], email, "staff", staff_id)
        print(f"  {email:<26} staff  {rank}")

    print(f"\nPassword for all of them: {PASSWORD}")


if __name__ == "__main__":
    main()
