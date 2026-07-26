-- ============================================================================
-- Emma AI · staff_certificates — per-staff certifications / qualifications
-- Feeds the Staff Portfolio "skills / verified credentials" UI. Standard tenant
-- RLS (own-facility only; service_role bypasses for seed/admin).
-- ============================================================================
create table if not exists staff_certificates (
    id          uuid primary key default gen_random_uuid(),
    facility_id uuid not null references facilities(id) on delete cascade,
    staff_id    uuid not null references staff(id) on delete cascade,
    cert_type   text not null,                          -- e.g. ACLS, BLS, Wound Care
    expiry_date date,
    file_url    text,
    created_at  timestamptz not null default now()
);
create index if not exists idx_staff_certificates_staff on staff_certificates(staff_id);

alter table staff_certificates enable row level security;
drop policy if exists staff_certificates_tenant on staff_certificates;
create policy staff_certificates_tenant on staff_certificates for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

grant select, insert, update, delete on staff_certificates to authenticated;
