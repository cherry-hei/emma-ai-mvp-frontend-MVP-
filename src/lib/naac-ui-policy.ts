/** Candidate-only NAAC identities. Never infer these from a job or auth role.
 * A future deployment must explicitly bind identities and enforce scope server-side.
 */
export const NAAC_UI_ROLES = ['superintendent', 'appointed_deputy', 'nurse', 'staff'] as const
export type NaacUiRole = (typeof NAAC_UI_ROLES)[number]
export const NAAC_UI_ACTIONS = [
  'personal_view', 'unit_view', 'organisation_view', 'batch_generate',
  'rules_dictionary', 'preliminary_review', 'reports_excel', 'audit',
  'staff_role_qualification_management', 'draft_shift_edit', 'final_decision', 'publish',
] as const
export type NaacUiAction = (typeof NAAC_UI_ACTIONS)[number]

export function isNaacUiRole(role: unknown): role is NaacUiRole {
  return typeof role === 'string' && (NAAC_UI_ROLES as readonly string[]).includes(role)
}

/** No canonical/legacy aliases, job-title parsing, or default grants. */
export function naacUiAllows(role: unknown, action: unknown): boolean {
  if (!isNaacUiRole(role) || !(NAAC_UI_ACTIONS as readonly unknown[]).includes(action)) return false
  if (action === 'personal_view' || action === 'unit_view') return true
  if (action === 'final_decision' || action === 'publish') return role === 'superintendent'
  if (action === 'draft_shift_edit') return role !== 'staff'
  return role === 'superintendent' || role === 'appointed_deputy'
}

export function naacUiScope(role: unknown): 'organisation' | 'unit' | 'none' {
  if (!isNaacUiRole(role)) return 'none'
  return role === 'superintendent' || role === 'appointed_deputy' ? 'organisation' : 'unit'
}
