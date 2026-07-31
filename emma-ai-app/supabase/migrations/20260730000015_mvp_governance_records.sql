-- ============================================================================
-- Emma AI · MVP governance records - the Phase 0 and 1.6 registers, populated
--
-- Reference data owned by a migration rather than by the application: an
-- architecture decision the app could rewrite is not a decision record, and a
-- scope lock the app could edit is not a lock. The API serves these read-only
-- (see api/routers/governance.py); the facility-scoped evidence rows at the end
-- are the only ones a superintendent can mark off.
--
-- Every insert is idempotent on its natural key so re-running the migration on a
-- database that already has these rows updates them instead of failing.
-- ============================================================================

-- ── 0.1 architecture decision ────────────────────────────────────────────────
insert into architecture_decisions
    (code, title, status, context, decision, consequences,
     alternatives_json, non_negotiables_json, decided_on, decided_by)
values (
    'ADR-0001',
    'PostgreSQL + Python for the 7-week MVP and Phase 2-4 growth',
    'accepted',
    'Rostering, staff, rules, audit and reporting are relational and heavily '
    'queried across facility boundaries that must never leak. The MVP has seven '
    'weeks, and the scheduling engine has to be callable from Python because the '
    'hard constraints are solved with CP-SAT. The product non-negotiables are '
    'outcomes, not vendors: delivery date, facility isolation, append-only '
    'auditability, compliance reporting, a Python-compatible rule engine, an '
    'async job path, HK/APAC readiness and maintainability.',
    'Managed PostgreSQL (Supabase) for data, authentication and row-level '
    'tenancy; FastAPI + emma_core for the domain and the OR-Tools CP-SAT solver; '
    'an async job table (optimization_jobs) rather than a broker, because the '
    'only long task today is the solver and polling a job row needs no extra '
    'infrastructure. Deterministic rules stay in the database and in Python; AI '
    'explains and suggests but can never override a hard constraint.',
    'Row-level security enforces tenancy at the database boundary, so an API bug '
    'cannot leak across facilities - but it also means every trusted server task '
    'must be explicit about using the service role. Publishing, leave balances '
    'and violation evidence are enforced by triggers, so importers and seeds have '
    'to satisfy real policy rather than bypass it. Swapping the managed provider '
    'later is a connection-string change plus a migration replay; swapping the '
    'relational model would not be.',
    '[
      {"option": "Firebase / document store",
       "why_not": "Roster, rule and audit queries are relational and cross-cutting; joins and constraints would move into application code."},
      {"option": "Self-managed Postgres on EC2",
       "why_not": "No operational headroom inside a 7-week MVP for backups, PITR, patching and connection pooling."},
      {"option": "Broker-backed worker queue (Celery/Redis) from day one",
       "why_not": "Only the solver is long-running; a job table plus polling meets the need with one less moving part. The path to a broker stays open."}
    ]'::jsonb,
    '[
      "7-week MVP delivery",
      "Secure role and facility isolation (RLS or equivalent, testable)",
      "Append-only auditability",
      "Compliance reporting fit for SWD review",
      "Python-compatible scheduling and rule engine",
      "Async job / worker path",
      "HK/APAC deployment readiness",
      "Future scalability and maintainability"
    ]'::jsonb,
    date '2026-05-30',
    'Kien (backend / AI / database)'
)
on conflict (code) do update set
    title = excluded.title, status = excluded.status,
    context = excluded.context, decision = excluded.decision,
    consequences = excluded.consequences,
    alternatives_json = excluded.alternatives_json,
    non_negotiables_json = excluded.non_negotiables_json,
    decided_on = excluded.decided_on, decided_by = excluded.decided_by,
    updated_at = now();

-- ── 0.2 MVP scope lock ───────────────────────────────────────────────────────
-- MVP = Phase 0-4 + Phase 7 reporting (data only) + the Staff App PWA backend.
-- Phase 5-6 and Phase 8 are outside the seven weeks; where they have already
-- landed the rationale says so, because a scope lock records what was committed,
-- not what happens to exist.
insert into project_scope (item_code, phase, title, scope, priority, rationale, agreed_on)
values
    ('0.1', 'Phase 0 - Decision & MVP Scope Lock', 'Architecture decision boundary', 'mvp', 'P0', 'ADR-0001 records the database/hosting/engine decision against the product outcomes.', date '2026-05-30'),
    ('0.2', 'Phase 0 - Decision & MVP Scope Lock', '7-week MVP scope lock', 'mvp', 'P0', 'This table is the lock.', date '2026-05-30'),
    ('1.1', 'Phase 1 - Foundation, Security & Data Import', 'Role-based login and permissions', 'mvp', 'P0', 'Supabase Auth + users_profile roles; enforcement documented as RLS-based.', date '2026-05-30'),
    ('1.2', 'Phase 1 - Foundation, Security & Data Import', 'Facility-level data isolation', 'mvp', 'P0', 'facility_id on every core table with RLS policies and isolation tests.', date '2026-05-30'),
    ('1.3', 'Phase 1 - Foundation, Security & Data Import', 'Append-only audit log', 'mvp', 'P0', 'audit_logs with before/after, actor and reason; UPDATE/DELETE blocked by trigger.', date '2026-05-30'),
    ('1.4', 'Phase 1 - Foundation, Security & Data Import', 'Import real roster Excel into the database', 'mvp', 'P0', 'emma_core.importers parses both homes'' layouts; import_jobs + import_issues carry the validation summary.', date '2026-05-30'),
    ('1.5', 'Phase 1 - Foundation, Security & Data Import', 'Calendar / public holiday & special-pay schema', 'mvp', 'P0', 'calendar_days feeds PH/SH handling, agency restrictions and cost multipliers.', date '2026-05-30'),
    ('1.6', 'Phase 1 - Foundation, Security & Data Import', 'Compliance / security evidence checklist', 'mvp', 'P1', 'evidence_items plus the evidence_pack report; caveats travel with the claims.', date '2026-05-30'),
    ('2.1', 'Phase 2 - Core Data Model', 'Staff profile and contract model', 'mvp', 'P0', 'staff, staff_contracts, staff_qualifications drive eligibility and rest rules.', date '2026-05-30'),
    ('2.2', 'Phase 2 - Core Data Model', 'Facility-specific JSON rule config', 'mvp', 'P0', 'facility_json_configs holds what a facility is; rule_definitions holds what the engine evaluates.', date '2026-05-30'),
    ('2.3', 'Phase 2 - Core Data Model', 'Shift definition dictionary', 'mvp', 'P0', 'shift_definitions with segments, paid_minutes and weighting_factor; minute-level overlap depends on it.', date '2026-05-30'),
    ('3.1', 'Phase 3 - Roster Operations', 'Database-backed roster calendar', 'mvp', 'P0', 'GET /rosters/{period} serves the staff x day grid from real rows.', date '2026-05-30'),
    ('3.2', 'Phase 3 - Roster Operations', 'Manual roster edit flow', 'mvp', 'P0', 'Cell CRUD writes manual_override_log so AI acceptance stays measurable.', date '2026-05-30'),
    ('3.3', 'Phase 3 - Roster Operations', 'Roster save, publish and export', 'mvp', 'P0', 'Publication is atomic and validation-gated; export is data-only for the MVP.', date '2026-05-30'),
    ('3.4', 'Phase 3 - Roster Operations', 'Limited A/B/C option comparison', 'mvp', 'P1', 'Kept because CP-SAT presets were already stable; would have been dropped before the delivery date.', date '2026-05-30'),
    ('4.1', 'Phase 4 - Task-Based Scheduling', 'Task-code definitions and assignment', 'mvp', 'P0', 'A1-A8 / P1-P6 eligibility, audit restrictions and the unaudited-agency rule.', date '2026-05-30'),
    ('4.2', 'Phase 4 - Task-Based Scheduling', 'Special event staffing overlays', 'mvp', 'P0', 'facility_events + event_staffing_requirements modify demand and show on the roster.', date '2026-05-30'),
    ('4.3', 'Phase 4 - Task-Based Scheduling', 'Floor / unit operational staffing', 'mvp', 'P0', 'floor_min_staffing_rules cover Home B''s 1/F, 2/F and 6/F minimums.', date '2026-05-30'),
    ('5.1', 'Phase 5 - Compliance Engine', 'SWD staffing ratio validation', 'deferred', 'P0', 'Outside the seven weeks; delivered early with the compliance engine.', date '2026-05-30'),
    ('5.2', 'Phase 5 - Compliance Engine', 'Hard constraint mapping', 'deferred', 'P0', 'Outside the seven weeks; delivered early with the compliance engine.', date '2026-05-30'),
    ('5.3', 'Phase 5 - Compliance Engine', 'Night shift continuity and compensation', 'deferred', 'P0', 'Outside the seven weeks; delivered early with the compliance engine.', date '2026-05-30'),
    ('5.4', 'Phase 5 - Compliance Engine', 'Agency / PT / imported labour restrictions', 'deferred', 'P0', 'Outside the seven weeks; delivered early with the compliance engine.', date '2026-05-30'),
    ('5.5', 'Phase 5 - Compliance Engine', 'Leave conflict, quota and priority rules', 'deferred', 'P0', 'Outside the seven weeks; delivered early with the compliance engine.', date '2026-05-30'),
    ('6.1', 'Phase 6 - AI Suggestion Layer', 'AI conflict explanation', 'deferred', 'P1', 'Deterministic rules remain the source of truth; explanations wait for an approved gateway.', date '2026-05-30'),
    ('6.2', 'Phase 6 - AI Suggestion Layer', 'AI-assisted replacement candidates', 'deferred', 'P0', 'The rule-based candidate ranking exists; the AI explanation layer does not.', date '2026-05-30'),
    ('7.1', 'Phase 7 - Reporting', 'Export basic compliance report', 'mvp', 'P0', 'Data only for the MVP: JSON + CSV. PDF/Excel rendering and object storage are deferred.', date '2026-05-30'),
    ('7.2', 'Phase 7 - Reporting', 'Export roster report', 'mvp', 'P1', 'Data only for the MVP: JSON + CSV of the published roster with task codes and events.', date '2026-05-30'),
    ('8.1', 'Phase 8 - QA, Evidence & Pilot Readiness', 'SWD / rule test fixtures', 'deferred', 'P0', 'pytest fixtures exist for the delivered rules; the full QA scope (ZAP, load, backup drill) is post-MVP.', date '2026-05-30'),
    ('8.2', 'Phase 8 - QA, Evidence & Pilot Readiness', 'Client / government evidence pack', 'deferred', 'P1', 'The checklist and its export exist; assembling and reviewing the pack is post-MVP.', date '2026-05-30'),
    ('SA.1', 'MVP addendum - Staff App PWA backend', 'Self-scoped staff endpoints', 'mvp', 'P0', 'Every /me/* route resolves the staff record from the caller''s own profile; RLS additionally restricts a staff login to its own rows.', date '2026-05-30')
on conflict (item_code) do update set
    phase = excluded.phase, title = excluded.title, scope = excluded.scope,
    priority = excluded.priority, rationale = excluded.rationale,
    agreed_on = excluded.agreed_on;

-- ── 1.6 evidence checklist (platform-wide controls) ──────────────────────────
-- facility_id is null: these are properties of the platform, so one tenant must
-- not be able to mark them off on another's behalf. Status reflects what the
-- repository can actually demonstrate today - nothing is marked pass on the
-- strength of an intention.
insert into evidence_items
    (facility_id, code, category, title, owner, test_method, sample_output,
     status, external_review_required, notes, sort_order)
values
    (null, 'EV-01', 'rbac', 'Role permission matrix enforced on every write path', 'Engineering', 'pytest: role-guarded endpoints reject non-permitted roles', 'tests/test_phase5_api_security.py', 'pass', false, 'Roles: superintendent, admin, scheduler, hr, auditor, staff.', 10),
    (null, 'EV-02', 'isolation', 'Facility isolation (row-level security)', 'Engineering', 'pytest: a Home A token cannot read or write Home B rows', 'tests/test_rls_isolation.py', 'pass', false, 'Enforced at the database boundary, not only in the API.', 20),
    (null, 'EV-03', 'audit', 'Append-only audit log with before/after and actor', 'Engineering', 'pytest: UPDATE and DELETE on audit_logs are rejected; GET /audit-logs returns the trail', 'GET /audit-logs; tests/test_mvp_foundation.py', 'pass', false, 'A correction is a further append, never a rewrite.', 30),
    (null, 'EV-04', 'rules', 'SWD staffing-ratio and hard-constraint fixtures', 'Engineering', 'pytest: minute-level ratio and every hard constraint against fixtures', 'tests/test_phase5_compliance.py; tests/test_phase5_validation.py', 'pass', false, 'Failed hard constraints block publication.', 40),
    (null, 'EV-05', 'api', 'API test report', 'Engineering', 'pytest: HTTP-level tests over the documented OpenAPI surface', 'tests/test_api.py', 'pass', false, null, 50),
    (null, 'EV-06', 'rules', 'Roster import validation summary', 'Engineering', 'pytest: both homes'' real layouts parse; unresolved cells are reported against their source cell', 'tests/test_mvp_import.py; import_issues', 'pass', false, 'A cell the parser cannot resolve is surfaced, never silently dropped.', 60),
    (null, 'EV-07', 'security', 'OWASP ZAP baseline scan', 'Engineering', 'ZAP baseline scan against the deployed API', null, 'pending', false, 'Not yet run against the deployed environment.', 70),
    (null, 'EV-08', 'backup', 'Backup and restore drill', 'Engineering', 'Restore a point-in-time snapshot into a scratch project and run the test suite against it', null, 'pending', false, 'Managed PITR is enabled; the restore drill is not yet evidenced.', 80),
    (null, 'EV-09', 'ai', 'AI prompt masking sample', 'Engineering', 'Prompt log review: no names, HKIDs or phone numbers leave the boundary', null, 'not_applicable', false, 'No AI explanation layer ships in the MVP (Phase 6). Becomes applicable when it does.', 90),
    (null, 'EV-10', 'security', 'Transport security configuration', 'Engineering', 'TLS configuration review of the deployed endpoints', null, 'pending', false, 'Target is TLS 1.2 minimum, TLS 1.3 where supported.', 100),
    (null, 'EV-11', 'audit', 'PDPO retention and deletion boundary', 'Product + legal', 'Written retention policy reviewed against HR, SWD-audit and statutory duties', null, 'pending', true, 'A 7-year audit retention period is proposed and needs client/legal confirmation. Deletion is not unconditional.', 110)
on conflict (coalesce(facility_id, '00000000-0000-0000-0000-000000000000'::uuid), code)
do update set
    category = excluded.category, title = excluded.title, owner = excluded.owner,
    test_method = excluded.test_method, sample_output = excluded.sample_output,
    status = excluded.status,
    external_review_required = excluded.external_review_required,
    notes = excluded.notes, sort_order = excluded.sort_order, updated_at = now();

-- Facility-scoped items: the ones a superintendent signs off for their own home.
insert into evidence_items
    (facility_id, code, category, title, owner, test_method, status,
     external_review_required, notes, sort_order)
select f.id, v.code, v.category, v.title, v.owner, v.test_method, 'pending',
       false, v.notes, v.sort_order
from facilities f
cross join (values
    ('EV-F1', 'rules', 'Facility rule profile reviewed by the RN advisor',
     'Superintendent', 'Walk the active rule set against the home''s own practice',
     'Ratio windows, night chain, agency caps and leave quotas are facility-scoped.', 200),
    ('EV-F2', 'isolation', 'User permission matrix signed off for this home',
     'Superintendent', 'Confirm each account''s role and that no account spans facilities',
     null, 210),
    ('EV-F3', 'audit', 'Resident-count source of truth confirmed',
     'Superintendent', 'Confirm who enters daily_resident_counts and how corrections are made',
     'The ratio denominator; a wrong count invalidates every ratio result.', 220)
) as v(code, category, title, owner, test_method, notes, sort_order)
on conflict (coalesce(facility_id, '00000000-0000-0000-0000-000000000000'::uuid), code)
do update set
    category = excluded.category, title = excluded.title, owner = excluded.owner,
    test_method = excluded.test_method, notes = excluded.notes,
    sort_order = excluded.sort_order, updated_at = now();
