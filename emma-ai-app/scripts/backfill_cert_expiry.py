"""One-off: backfill staff_certificates.expiry_date for the demo Home A certs.

Non-destructive — only sets expiry_date on existing rows (matches seed.py values) so
the Compliance "Certifications" expiry view has real data without a full reseed.
Safe to delete after running.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core.db import get_service_client  # noqa: E402

EXPIRY = {
    "ACLS": "2026-08-10", "Triage": "2027-01-15", "BLS": "2026-08-01",
    "First Aid": "2026-08-20", "Manual Handling": "2027-03-01",
    "Elder Care": "2026-09-30", "Vitals": "2026-08-15", "Personal Care": "2027-06-30",
    "Rehab Tech": "2026-11-05", "Bathing": "2026-08-28", "Transfer": "2027-02-01",
    "Infection Control": "2027-01-20",
}

sb = get_service_client()
rows = sb.table("staff_certificates").select("id,cert_type,expiry_date").execute().data
n = 0
for r in rows:
    exp = EXPIRY.get(r["cert_type"])
    if exp and not r.get("expiry_date"):
        sb.table("staff_certificates").update({"expiry_date": exp}).eq("id", r["id"]).execute()
        n += 1
print(f"backfilled {n} cert expiry dates")
