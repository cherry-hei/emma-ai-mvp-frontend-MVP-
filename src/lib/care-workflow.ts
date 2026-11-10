import type { Feature, Grant } from './permissions'

/** Server-reviewed tenant and appointment context. A display name never grants access. */
export interface CareWorkflow {
  status: 'ready' | 'unbound' | 'invalid'
  care_home: 'A' | 'B' | null
  workflow: 'SA' | 'NAAC' | null
  role: string | null
  role_label: { en: string; zh: string }
  org_id: string | null
  facility_id: string | null
  unit_ids: string[]
  permissions: Partial<Record<Feature, Grant>>
  actions: Record<string, boolean>
  roster_scope: 'facility' | 'self_and_units' | 'self' | 'none'
}

type Identity = { orgId: string | null; facilityId: string | null }
const GRANTS = new Set(['F', 'R', 'E', 'V', 'S', '-'])
const SCOPES = new Set(['facility', 'self_and_units', 'self', 'none'])

/** Missing/old API contracts and tenant mismatches are denied, never mapped by home labels. */
export function readCareWorkflow(value: unknown, identity: Identity): CareWorkflow | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const v = value as Record<string, unknown>
  if (!['ready', 'unbound', 'invalid'].includes(String(v.status))) return null
  if (v.status !== 'ready') return null
  if (!identity.orgId || !identity.facilityId || v.org_id !== identity.orgId || v.facility_id !== identity.facilityId) return null
  if (!((v.care_home === 'A' && v.workflow === 'SA') || (v.care_home === 'B' && v.workflow === 'NAAC'))) return null
  if (typeof v.role !== 'string' || !v.role) return null
  const labels = v.role_label as Record<string, unknown> | undefined
  if (!labels || typeof labels.en !== 'string' || typeof labels.zh !== 'string') return null
  if (!Array.isArray(v.unit_ids) || !v.unit_ids.every(id => typeof id === 'string' && id.length > 0)) return null
  if (!SCOPES.has(String(v.roster_scope))) return null
  if (!v.permissions || typeof v.permissions !== 'object' || Array.isArray(v.permissions)) return null
  if (!Object.values(v.permissions).every(grant => GRANTS.has(String(grant)))) return null
  if (!v.actions || typeof v.actions !== 'object' || Array.isArray(v.actions)) return null
  if (!Object.values(v.actions).every(action => typeof action === 'boolean')) return null
  return value as CareWorkflow
}

export function workflowAction(workflow: CareWorkflow | null | undefined, action: string): boolean {
  return workflow?.status === 'ready' && workflow.actions[action] === true
}

export function workflowLabel(workflow: CareWorkflow | null | undefined): string {
  return workflow?.status === 'ready' ? `Care Home ${workflow.care_home} · ${workflow.workflow}` : ''
}

/** Calendar-day periods preserve the actual SA/NAAC rule engine cycle. */
export function workflowPeriod(workflow: CareWorkflow | null | undefined, start: string): {
  period_start: string; period_end: string; cycle_type: '28day' | '42day'
} | null {
  if (workflow?.status !== 'ready' || !/^\d{4}-\d{2}-\d{2}$/.test(start)) return null
  const isNAAC = workflow.care_home === 'B' && workflow.workflow === 'NAAC'
  if (!isNAAC && !(workflow.care_home === 'A' && workflow.workflow === 'SA')) return null
  const date = new Date(`${start}T00:00:00Z`)
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== start) return null
  date.setUTCDate(date.getUTCDate() + (isNAAC ? 41 : 27))
  return { period_start: start, period_end: date.toISOString().slice(0, 10), cycle_type: isNAAC ? '42day' : '28day' }
}
