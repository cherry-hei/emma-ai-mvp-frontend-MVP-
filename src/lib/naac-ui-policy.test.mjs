import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { NAAC_UI_ACTIONS, naacUiAllows, naacUiScope } from './naac-ui-policy.ts'

const expected = {
  superintendent: [1,1,1,1,1,1,1,1,1,1,1,1],
  appointed_deputy: [1,1,1,1,1,1,1,1,1,1,0,0],
  nurse: [1,1,0,0,0,0,0,0,0,1,0,0],
  staff: [1,1,0,0,0,0,0,0,0,0,0,0],
}
const actions = ['personal_view', 'unit_view', 'organisation_view', 'batch_generate', 'rules_dictionary', 'preliminary_review', 'reports_excel', 'audit', 'staff_role_qualification_management', 'draft_shift_edit', 'final_decision', 'publish']
for (const [role, grants] of Object.entries(expected)) {
  test(`${role}: exact confirmed 12-action matrix`, () => {
    assert.deepEqual(NAAC_UI_ACTIONS, actions)
    actions.forEach((action, index) => assert.equal(naacUiAllows(role, action), Boolean(grants[index]), action))
  })
}
test('unknown roles, canonical roles and job titles never acquire NAAC authority', () => {
  for (const role of [undefined, null, '', 'OWNER', 'NURSE_MGR', 'SW1', 'SW', 'deputy', 'appointedDeputy', 'Superintendent', ' superintendent', {}, '__proto__']) {
    actions.forEach(action => assert.equal(naacUiAllows(role, action), false))
    assert.equal(naacUiScope(role), 'none')
  }
  assert.equal(naacUiAllows('superintendent', 'invite'), false)
  assert.equal(naacUiAllows('superintendent', 'roi'), false)
  assert.equal(naacUiAllows('superintendent', '__proto__'), false)
})
test('scope is organisation only for superintendent and explicitly appointed deputy', () => {
  assert.equal(naacUiScope('superintendent'), 'organisation')
  assert.equal(naacUiScope('appointed_deputy'), 'organisation')
  assert.equal(naacUiScope('nurse'), 'unit')
  assert.equal(naacUiScope('staff'), 'unit')
})
test('preview uses existing facility.settings guard and keeps unknown routes fail closed', () => {
  const routes = readFileSync(new URL('../components/layout/navRoutes.ts', import.meta.url), 'utf8')
  const shell = readFileSync(new URL('../components/layout/AppShell.tsx', import.meta.url), 'utf8')
  assert.match(routes, /naacAccessPreview: '\/naac-access-preview'/)
  assert.match(routes, /\[ROUTES.naacAccessPreview\]: 'facility.settings'/)
  assert.match(shell, /feature === undefined \|\| !canOpenRoute\(user\?\.role, feature\)/)
  const permissions = readFileSync(new URL('./permissions.ts', import.meta.url), 'utf8')
  assert.match(permissions, /'facility.settings':\s+row\('F', '-', '-', '-', '-', '-', '-'\)/)
})
