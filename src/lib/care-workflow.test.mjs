import assert from 'node:assert/strict'
import test from 'node:test'
import { readCareWorkflow, workflowAction, workflowLabel, workflowPeriod } from './care-workflow.ts'
import { canRead, canDecide, canRecommend, canWrite, isSelfOnly } from './permissions.ts'

const identity = { orgId: 'org-naac', facilityId: 'facility-naac' }
function binding(overrides = {}) {
  return {
    status: 'ready', care_home: 'B', workflow: 'NAAC', role: 'deputy',
    role_label: { en: 'Appointed deputy', zh: '獲委任副手' },
    org_id: identity.orgId, facility_id: identity.facilityId, unit_ids: [],
    permissions: { 'roster.view': 'V', 'reports': 'V', 'approve.leave': 'R', 'roster.publish': '-' },
    actions: { roster_edit: true, roster_generate: true, roster_publish: false },
    roster_scope: 'facility', ...overrides,
  }
}

test('an OWNER-backed NAAC deputy can recommend but cannot final-approve or publish', () => {
  const careWorkflow = readCareWorkflow(binding(), identity)
  const user = { role: 'OWNER', careWorkflow }
  assert.equal(canRead(user, 'reports'), true)
  assert.equal(canRecommend(user, 'approve.leave'), true)
  assert.equal(canDecide(user, 'approve.leave'), false)
  assert.equal(workflowAction(careWorkflow, 'roster_publish'), false)
  assert.equal(workflowLabel(careWorkflow), 'Care Home B · NAAC')
})

test('missing or unbound workflow never falls back to a broad legacy role', () => {
  for (const raw of [undefined, null, binding({ status: 'unbound' }), binding({ status: 'invalid' })]) {
    const user = { role: 'OWNER', careWorkflow: readCareWorkflow(raw, identity) }
    assert.equal(canRead(user, 'roster.view'), false)
    assert.equal(canDecide(user, 'approve.leave'), false)
  }
})

test('a workflow from another organisation/facility or A/B mapping is rejected', () => {
  for (const raw of [binding({ org_id: 'other-org' }), binding({ facility_id: 'other-home' }), binding({ care_home: 'A' }), binding({ workflow: 'SA' })]) {
    assert.equal(readCareWorkflow(raw, identity), null)
  }
  assert.equal(readCareWorkflow(binding(), { orgId: null, facilityId: identity.facilityId }), null)
})

test('NAAC nurse edits permitted shifts without generation, deletion or final decisions', () => {
  const careWorkflow = readCareWorkflow(binding({ role: 'nurse', unit_ids: ['unit-one'], roster_scope: 'self_and_units',
    permissions: { 'roster.view': 'V', 'roster.ai_draft': '-', 'approve.leave': '-', 'roster.publish': '-' },
    actions: { roster_edit: true, roster_generate: false, roster_batch: false, roster_publish: false, roster_delete: false },
  }), identity)
  const user = { role: 'NURSE_MGR', careWorkflow }
  assert.equal(workflowAction(careWorkflow, 'roster_edit'), true)
  for (const action of ['roster_generate', 'roster_batch', 'roster_publish', 'roster_delete']) assert.equal(workflowAction(careWorkflow, action), false)
  assert.equal(canWrite(user, 'roster.ai_draft'), false)
  assert.equal(canDecide(user, 'approve.leave'), false)
})

test('staff self-only grants do not open facility management screens', () => {
  const careWorkflow = readCareWorkflow(binding({ role: 'staff', permissions: { 'roster.view': 'S' }, roster_scope: 'self' }), identity)
  assert.equal(canRead({ role: 'FRONTLINE', careWorkflow }, 'roster.view'), false)
  assert.equal(isSelfOnly({ role: 'FRONTLINE', careWorkflow }, 'roster.view'), true)
})

test('malformed grants/actions fail closed while an explicit SA A binding remains valid', () => {
  for (const raw of [binding({ permissions: { 'roster.view': 'FULL' } }), binding({ actions: { roster_publish: 'true' } }), binding({ unit_ids: [null] })]) {
    assert.equal(readCareWorkflow(raw, identity), null)
  }
  assert.equal(workflowLabel(readCareWorkflow(binding({ care_home: 'A', workflow: 'SA', role: 'OWNER' }), identity)), 'Care Home A · SA')
})

test('NAAC gets all 42 calendar dates across a year boundary, SA keeps 28 days', () => {
  const naac = readCareWorkflow(binding(), identity)
  assert.deepEqual(workflowPeriod(naac, '2026-12-15'), {
    period_start: '2026-12-15', period_end: '2027-01-25', cycle_type: '42day',
  })
  const sa = readCareWorkflow(binding({ care_home: 'A', workflow: 'SA', role: 'OWNER' }), identity)
  assert.deepEqual(workflowPeriod(sa, '2026-12-15'), {
    period_start: '2026-12-15', period_end: '2027-01-11', cycle_type: '28day',
  })
})

test('an unbound home or invalid date cannot create a roster cycle', () => {
  assert.equal(workflowPeriod(null, '2026-11-10'), null)
  assert.equal(workflowPeriod(readCareWorkflow(binding(), identity), '2026-02-30'), null)
  assert.equal(workflowPeriod(readCareWorkflow(binding(), identity), ''), null)
})
