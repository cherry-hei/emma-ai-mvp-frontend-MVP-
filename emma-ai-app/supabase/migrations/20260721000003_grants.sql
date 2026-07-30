-- ============================================================================
-- Emma AI · Phase 0 - role grants for PostgREST/Supabase roles
-- RLS still enforces per-facility row scoping; these are table-level privileges
-- the API roles need to reach the tables at all.
--   service_role  -> full access (bypasses RLS by design; used for admin/seed)
--   authenticated -> CRUD (rows then filtered by RLS policies)
--   anon          -> none (app requires login)
-- ============================================================================

grant usage on schema public to anon, authenticated, service_role;

grant all privileges on all tables in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;

grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- Future tables (later migrations) inherit the same grants automatically.
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public
    grant select, insert, update, delete on tables to authenticated;
