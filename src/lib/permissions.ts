// Frontend mirror of emma_core/permissions.py (spec 1.1).
//
// Source of truth is "Emma AI - RBAC Definition for Implementation
// (Salvation Army x NAAC)", 30 Jul 2026. The backend enforces it; this file
// exists so the menu never offers a route the API will refuse, and so a hidden
// route is hidden rather than merely unlinked.
//
// Hiding a menu item is not a security control - the backend guard is. Both are
// required: the API stops the request, this stops the user being shown a door
// that does not open.

export const SYSTEM_ROLES = [
  'OWNER', 'NURSE_MGR', 'ALLIED_HEALTH', 'ADMIN_CLERK',
  'SCHEDULER', 'FRONTLINE', 'HR_AUDITOR',
] as const

export type SystemRole = (typeof SYSTEM_ROLES)[number]

/** F full · R recommend · E edit · V view · S self-only · '-' hidden */
export type Grant = 'F' | 'R' | 'E' | 'V' | 'S' | '-'

// Legacy `profiles.role` values still held by seeded and existing accounts.
// Mirrors LEGACY_ROLE_ALIASES on the backend; both generations resolve here so a
// signed-in superintendent is treated as OWNER without a data migration first.
const LEGACY_ALIASES: Record<string, SystemRole> = {
  superintendent: 'OWNER',
  admin: 'ADMIN_CLERK',
  staff: 'FRONTLINE',
  scheduler: 'SCHEDULER',
  hr: 'HR_AUDITOR',
  auditor: 'HR_AUDITOR',
}

export function normaliseRole(role: string | null | undefined): SystemRole | null {
  if (!role) return null
  const raw = role.trim()
  if (!raw) return null
  const upper = raw.toUpperCase() as SystemRole
  if ((SYSTEM_ROLES as readonly string[]).includes(upper)) return upper
  return LEGACY_ALIASES[raw.toLowerCase()] ?? null
}

// Only the features the UI actually gates on. The backend holds the full table;
// duplicating all 29 rows here would create two things to keep in step for no
// gain, since the API is what decides.
export type Feature =
  | 'dashboard'
  | 'roster.view'
  | 'roster.ai_draft'
  | 'roster.publish'
  | 'approve.leave'
  | 'staff.portfolio'
  | 'staff.profile_write'
  | 'reports'
  | 'compliance'
  | 'alerts'
  | 'roi'
  | 'audit_log'
  | 'task_codes'

type Row = Record<SystemRole, Grant>

const row = (
  OWNER: Grant, NURSE_MGR: Grant, ALLIED_HEALTH: Grant, ADMIN_CLERK: Grant,
  SCHEDULER: Grant, FRONTLINE: Grant, HR_AUDITOR: Grant,
): Row => ({ OWNER, NURSE_MGR, ALLIED_HEALTH, ADMIN_CLERK, SCHEDULER, FRONTLINE, HR_AUDITOR })

// SCHEDULER and HR_AUDITOR columns are PROVISIONAL: the source document defines
// both roles but ships no matrix columns for them. Values match the backend's
// _PROVISIONAL block and await client confirmation.
//                        OWNER NURSE ALLIED CLERK SCHED FRONT HRAUD
const MATRIX: Record<Feature, Row> = {
  'dashboard':           row('F', 'V', 'V', 'V', 'V', '-', 'V'),
  'roster.view':         row('F', 'V', 'V', 'V', 'V', 'S', 'V'),
  'roster.ai_draft':     row('F', 'E', '-', '-', 'E', '-', '-'),
  'roster.publish':      row('F', '-', '-', '-', '-', '-', '-'),
  'approve.leave':       row('F', 'R', '-', 'R', '-', 'S', '-'),
  'staff.portfolio':     row('F', 'V', 'V', 'E', 'V', 'S', 'V'),
  'staff.profile_write': row('F', '-', '-', 'E', '-', '-', '-'),
  'reports':             row('F', 'V', '-', 'V', 'V', '-', 'V'),
  'compliance':          row('F', 'V', 'V', 'V', 'V', '-', 'V'),
  'alerts':              row('F', 'V', '-', 'V', '-', 'S', 'V'),
  'roi':                 row('F', '-', '-', '-', '-', '-', '-'),
  'audit_log':           row('F', '-', '-', '-', '-', '-', 'V'),
  'task_codes':          row('F', 'E', 'E', 'V', 'V', 'S', 'V'),
}

const READ: ReadonlySet<Grant> = new Set<Grant>(['F', 'R', 'E', 'V'])
const WRITE: ReadonlySet<Grant> = new Set<Grant>(['F', 'E'])

/** Unknown role or unknown feature denies - never default open. */
export function grantFor(role: string | null | undefined, feature: Feature): Grant {
  const resolved = normaliseRole(role)
  if (!resolved) return '-'
  return MATRIX[feature]?.[resolved] ?? '-'
}

/** Facility-wide read. `S` is excluded: self-only is not a facility read. */
export function canRead(role: string | null | undefined, feature: Feature): boolean {
  return READ.has(grantFor(role, feature))
}

export function canWrite(role: string | null | undefined, feature: Feature): boolean {
  return WRITE.has(grantFor(role, feature))
}

/** Final approve/reject/cancel/revoke. OWNER only, by design - the rest recommend. */
export function canDecide(role: string | null | undefined, feature: Feature): boolean {
  return grantFor(role, feature) === 'F'
}

export function canRecommend(role: string | null | undefined, feature: Feature): boolean {
  const g = grantFor(role, feature)
  return g === 'F' || g === 'R'
}

/** True when the caller sees the feature but only their own rows. */
export function isSelfOnly(role: string | null | undefined, feature: Feature): boolean {
  return grantFor(role, feature) === 'S'
}

/** Reachable at all, self-only included. Drives menu visibility. */
export function isVisible(role: string | null | undefined, feature: Feature): boolean {
  return grantFor(role, feature) !== '-'
}
