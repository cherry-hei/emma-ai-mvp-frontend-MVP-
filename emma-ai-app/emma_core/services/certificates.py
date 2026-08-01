"""The certificate vault and its expiry warnings (spec SA.7).

`staff_certificates` has existed since migration 6, but only ever as something
five other services *read* - the compliance engine, the staff-app profile, the
insights panel and two reports all ask when a certificate expires. Nothing wrote
to it except the seed, so in practice the expiry dates were whatever the fixture
said and nobody was ever told a certificate had lapsed.

This module is the write side and the warning side.

Why the warning is a ladder, not a threshold
--------------------------------------------
A single "expires within 30 days" alert has two failure modes and hits both. Sent
once, it is forgotten in a busy week. Sent every day for 30 days, it is muted by
day three, and the mute carries over to the certificate that matters.

So each certificate crosses a fixed set of stages - 90, 60, 30, 14, 7 days, the
day it expires, then weekly while it stays expired - and each stage notifies
exactly once. `notified_stage` on the row records how far it has got, which makes
the job idempotent: running it twice in a day, or twice after a crash, sends
nothing the second time.

Who hears about it
------------------
The staff member, always - it is their certificate and usually their renewal to
book. Plus whoever the permission matrix says may act on staff records, because
an expired certificate is a rostering problem before it is an HR one: a lapsed
medication audit means the person cannot be rostered on a drug round tomorrow.
"""
from __future__ import annotations

from datetime import date as Date, timedelta

from ..permissions import Feature
from . import notifications
from ._common import iso

# Days before expiry at which a warning is sent. Ascending, and read that way:
# a certificate falls into the *tightest* band it has reached, so 60 days out is
# 'd60' and not 'd90'. Reading it the other way puts everything under 90 days in
# the d90 band, which fires once and then never escalates.
WARNING_STAGES: tuple[int, ...] = (7, 14, 30, 60, 90)

# Once expired, the reminder repeats on this cadence rather than falling silent.
EXPIRED_REPEAT_DAYS = 7

# Certificates whose lapse changes what a person may be rostered onto, rather
# than only what HR has on file. These escalate to managers at every stage; the
# rest only escalate once they are inside 30 days.
ROSTER_CRITICAL = {"BLS", "ACLS", "MEDICATION_AUDIT", "FIRST_AID", "MANUAL_HANDLING"}

MANAGER_ESCALATION_DAYS = 30


def _as_date(value) -> Date | None:
    if not value:
        return None
    if isinstance(value, Date):
        return value
    return Date.fromisoformat(str(value)[:10])


def stage_for(days_left: int | None) -> str | None:
    """Which warning stage a certificate is at, or None if it is not due one.

    Returned as a string because it is stored on the row and compared for
    equality; `'expired:2'` is the second weekly reminder after lapse, and
    encoding the repeat count in the stage is what stops the weekly reminder
    firing every day.
    """
    if days_left is None:
        return None
    if days_left < 0:
        return f"expired:{(-days_left - 1) // EXPIRED_REPEAT_DAYS + 1}"
    if days_left == 0:
        return "expires_today"
    for threshold in WARNING_STAGES:
        if days_left <= threshold:
            return f"d{threshold}"
    return None


# ── vault CRUD ───────────────────────────────────────────────────────────────
def list_for_staff(client, facility_id: str, staff_id: str, *,
                   today: Date | None = None) -> list[dict]:
    today = today or Date.today()
    # SQL: select * from staff_certificates
    #      where facility_id = :facility_id and staff_id = :staff_id
    #      order by expiry_date nulls last
    rows = (client.table("staff_certificates").select("*")
            .eq("facility_id", facility_id).eq("staff_id", staff_id)
            .order("expiry_date").execute().data)
    return [_decorate(row, today) for row in rows]


def _decorate(row: dict, today: Date) -> dict:
    expiry = _as_date(row.get("expiry_date"))
    days_left = (expiry - today).days if expiry else None
    return {
        **row,
        "days_left": days_left,
        "is_expired": days_left is not None and days_left < 0,
        "stage": stage_for(days_left),
    }


def upsert(client, facility_id: str, staff_id: str, *, cert_type: str,
           expiry_date=None, file_url: str | None = None,
           certificate_id: str | None = None) -> dict:
    """Add a certificate, or replace the one of the same type.

    One row per (staff, cert_type): a renewal is an update, not a second row.
    Keeping both would leave every reader - the compliance engine included -
    having to decide which of two BLS certificates is the real one, and the
    obvious tie-break (latest expiry) is wrong for a certificate that was
    re-issued with a shorter term.

    Renewing resets `notified_stage`, so the new expiry gets its own full ladder
    of warnings instead of inheriting the old one's progress.
    """
    cert_type = (cert_type or "").strip().upper()
    if not cert_type or len(cert_type) > 64:
        raise ValueError("cert_type must be 1-64 characters")
    expiry = _as_date(expiry_date)
    row = {
        "facility_id": facility_id, "staff_id": staff_id, "cert_type": cert_type,
        "expiry_date": iso(expiry) if expiry else None,
        "file_url": (file_url or "").strip() or None,
        "notified_stage": None,
    }
    if certificate_id:
        # SQL: update staff_certificates set ...
        #      where facility_id = :facility_id and id = :certificate_id returning *
        rows = (client.table("staff_certificates").update(row)
                .eq("facility_id", facility_id).eq("id", certificate_id)
                .execute().data)
        if not rows:
            raise ValueError("certificate not found")
        return _decorate(rows[0], Date.today())

    # SQL: select id from staff_certificates
    #      where facility_id = :f and staff_id = :s and cert_type = :cert_type
    existing = (client.table("staff_certificates").select("id")
                .eq("facility_id", facility_id).eq("staff_id", staff_id)
                .eq("cert_type", cert_type).execute().data)
    if existing:
        rows = (client.table("staff_certificates").update(row)
                .eq("id", existing[0]["id"]).execute().data)
        return _decorate(rows[0], Date.today())
    # SQL: insert into staff_certificates (...) values (...) returning *
    return _decorate(
        client.table("staff_certificates").insert(row).execute().data[0],
        Date.today())


def delete(client, facility_id: str, certificate_id: str) -> None:
    # SQL: delete from staff_certificates
    #      where facility_id = :facility_id and id = :certificate_id
    (client.table("staff_certificates").delete()
     .eq("facility_id", facility_id).eq("id", certificate_id).execute())


# ── expiry sweep ─────────────────────────────────────────────────────────────
def expiring(client, facility_id: str, *, within_days: int = 90,
             include_expired: bool = True, today: Date | None = None) -> list[dict]:
    """Certificates due or overdue, soonest first. Drives the manager dashboard."""
    today = today or Date.today()
    horizon = today + timedelta(days=within_days)
    query = (client.table("staff_certificates").select("*")
             .eq("facility_id", facility_id)
             .not_.is_("expiry_date", "null")
             .lte("expiry_date", iso(horizon)))
    if not include_expired:
        query = query.gte("expiry_date", iso(today))
    rows = query.order("expiry_date").execute().data
    return [_decorate(row, today) for row in rows]


def _staff_names(client, facility_id: str, staff_ids: list[str]) -> dict[str, str]:
    if not staff_ids:
        return {}
    # SQL: select id, name, name_en from staff
    #      where facility_id = :facility_id and id = any(:staff_ids)
    rows = (client.table("staff").select("id,name,name_en")
            .eq("facility_id", facility_id).in_("id", staff_ids).execute().data)
    return {r["id"]: (r.get("name") or r.get("name_en") or "") for r in rows}


def _message(cert_type: str, days_left: int, name: str) -> tuple[str, str]:
    who = f"{name}'s " if name else "Your "
    if days_left < 0:
        return (f"{cert_type} has expired",
                f"{who}{cert_type} expired {-days_left} day"
                f"{'s' if days_left != -1 else ''} ago and must be renewed before "
                "the next roster is published.")
    if days_left == 0:
        return (f"{cert_type} expires today",
                f"{who}{cert_type} expires today.")
    return (f"{cert_type} expires in {days_left} days",
            f"{who}{cert_type} expires on the {days_left}-day mark. Book the "
            "renewal now to avoid a rostering restriction.")


def notify_expiring(client, facility_id: str, *, today: Date | None = None,
                    dry_run: bool = False) -> list[dict]:
    """Send each certificate's next due warning. Idempotent within a stage.

    Returns one entry per certificate notified, so a scheduled run can be logged
    and a dry run can be inspected before the first real send.
    """
    today = today or Date.today()
    due = expiring(client, facility_id, within_days=max(WARNING_STAGES), today=today)
    names = _staff_names(client, facility_id, [c["staff_id"] for c in due])

    sent: list[dict] = []
    for cert in due:
        stage = cert["stage"]
        if not stage or stage == cert.get("notified_stage"):
            continue
        days_left = cert["days_left"]
        name = names.get(cert["staff_id"], "")
        title, body = _message(cert["cert_type"], days_left, name)
        record = {
            "certificate_id": cert["id"], "staff_id": cert["staff_id"],
            "cert_type": cert["cert_type"], "days_left": days_left, "stage": stage,
            "escalated": _escalates(cert["cert_type"], days_left),
        }
        if dry_run:
            sent.append(record)
            continue

        notifications.push(
            client, facility_id, staff_id=cert["staff_id"],
            event_type="certificate_expiry", title=title, body=body,
            related_type="staff_certificates", related_id=cert["id"])
        if record["escalated"]:
            notifications.push_to_approvers(
                client, facility_id, Feature.STAFF_PORTFOLIO,
                event_type="certificate_expiry", title=title, body=body,
                related_type="staff_certificates", related_id=cert["id"])
        # Written last. If the push fails, the stage stays where it was and the
        # next run retries - a repeated warning is recoverable, a silently
        # skipped one is not.
        # SQL: update staff_certificates set notified_stage = :stage,
        #          notified_at = now() where id = :id
        (client.table("staff_certificates")
         .update({"notified_stage": stage, "notified_at": iso(today)})
         .eq("id", cert["id"]).execute())
        sent.append(record)
    return sent


def _escalates(cert_type: str, days_left: int) -> bool:
    """Managers hear about a roster-critical certificate at every stage, and any
    other certificate once it is inside 30 days."""
    if (cert_type or "").upper() in ROSTER_CRITICAL:
        return True
    return days_left <= MANAGER_ESCALATION_DAYS
