-- ─────────────────────────────────────────────────────────────────────────────
-- SA.7, second pass: the staff member's own vault.
--
-- The ticket asks for a certificate vault that FRONTLINE fills in themselves -
-- "Staff upload their own certificates ... FRONTLINE self-only upload/view".
-- Migration 19 built the vault and the expiry ladder, but everything that reads
-- or writes it is facility-scoped, so the person whose certificate it is could
-- not file one. Two things were missing and one was wrong.
--
-- 1. The certificate number was never stored. The ticket lists it beside the
--    type and the dates, and it is the field the Nursing Council registry is
--    checked against - a vault that cannot answer "which practising certificate
--    is this?" fails the audit it exists for.
--
-- 2. The RLS policy is `facility_id = current_facility_id()` and nothing else,
--    so any authenticated token in the home can read every colleague's
--    certificates, and a care worker's phone could enumerate the lot. The
--    matrix puts FRONTLINE at S on staff.certificates - self only. Every other
--    table holding personal rows already guards with can_see_staff_row(); this
--    one was missed because until migration 19 nothing wrote to it.
--
--    can_see_staff_row() is the right guard rather than a role list: it lets
--    every non-staff role through (the matrix decides what they may do at the
--    API) and narrows a staff token to its own staff_id.
-- ─────────────────────────────────────────────────────────────────────────────

alter table staff_certificates
    -- Practising certificate / BLS card number as printed on the document.
    -- Nullable: the seeded and imported rows do not have one, and refusing them
    -- would empty a vault five services already read.
    add column if not exists cert_number text;

comment on column staff_certificates.cert_number is
    'Certificate number as printed on the document. Nullable - seeded and imported rows predate it.';

-- Tighten the tenant policy to a per-person one. Managers, clerks and HR are
-- unaffected; a staff token now sees only its own rows.
drop policy if exists staff_certificates_tenant on staff_certificates;
create policy staff_certificates_tenant on staff_certificates for all to authenticated
    using (facility_id = public.current_facility_id()
           and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id()
                and public.can_see_staff_row(staff_id));
