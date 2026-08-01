-- ─────────────────────────────────────────────────────────────────────────────
-- MVP SA.7 · certificate vault and expiry notification
--
-- `staff_certificates` has been read by five services since migration 6 - the
-- compliance engine, the staff-app profile, insights and two reports all ask
-- when a certificate expires - but nothing ever wrote to it outside the seed,
-- and nobody was ever told a certificate had lapsed.
--
-- Two columns make the warning job idempotent. Without them the choice is a
-- daily re-send (muted by day three, and the mute carries to the certificate
-- that matters) or a single alert that is forgotten in a busy week.
-- ─────────────────────────────────────────────────────────────────────────────

alter table staff_certificates
    -- How far up the warning ladder this certificate has been told: 'd90',
    -- 'd60', 'd30', 'd14', 'd7', 'expires_today', then 'expired:1', 'expired:2'…
    -- weekly. Cleared on renewal so a new expiry gets a fresh ladder.
    add column if not exists notified_stage text,
    add column if not exists notified_at    date,
    -- Who filed it, and when it was issued. Both nullable: the seeded rows and
    -- the imported ones have neither, and refusing those would empty the vault.
    add column if not exists issued_date    date,
    add column if not exists uploaded_by    uuid references users_profile(id) on delete set null,
    add column if not exists notes          text;

-- One row per (staff, certificate type): a renewal updates the row rather than
-- adding a second. Two live BLS certificates would leave every reader deciding
-- which is real, and the obvious tie-break (latest expiry) is wrong for one
-- re-issued on a shorter term.
--
-- Built concurrently-unsafe on purpose: this table is small and the migration
-- runs at deploy, not against live traffic.
create unique index if not exists uq_staff_certificates_staff_type
    on staff_certificates(staff_id, cert_type);

-- The expiry sweep reads "everything due before X, soonest first", per facility.
create index if not exists idx_staff_certificates_expiry
    on staff_certificates(facility_id, expiry_date)
    where expiry_date is not null;

comment on column staff_certificates.notified_stage is
    'Last expiry-warning stage sent for THIS expiry date. Reset to null on renewal so the ladder restarts. Makes notify_expiring() idempotent within a stage.';
