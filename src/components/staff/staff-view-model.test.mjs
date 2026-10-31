import assert from 'node:assert/strict'
import test from 'node:test'
import {
  knownStatusLabel,
  matchesStaffDirectoryFilter,
  sourceHours,
  staffInitials,
  toStaffDirectoryCard,
} from './staff-view-model.ts'

const apiRow = {
  id: 'staff-tenant-a-47',
  name: '陳小明',
  name_en: 'Chan Siu Ming',
  rank: 'PCW',
  employment_type: 'local_pt',
  unit_name: 'North Wing',
  status: 'scheduled',
  is_audited_for_medication: false,
  is_mentor: true,
  certs: ['BLS', 'First Aid'],
  certificates: [],
  scheduled_hours: 7.5,
  contracted_period_hours: 0,
}

test('staff cards preserve the tenant API identity, role code, and returned zero hours', () => {
  const card = toStaffDirectoryCard(apiRow)

  assert.deepEqual(card, {
    id: 'staff-tenant-a-47',
    primaryName: 'Chan Siu Ming',
    secondaryName: '陳小明',
    roleCode: 'PCW',
    employmentType: 'local_pt',
    unitName: 'North Wing',
    status: 'scheduled',
    certificates: ['BLS', 'First Aid'],
    scheduledHours: 7.5,
    contractedPeriodHours: 0,
  })
  assert.equal(staffInitials(card), 'CS')
  assert.equal(sourceHours(card.contractedPeriodHours, 'Not provided'), '0 h')
  assert.equal(knownStatusLabel('scheduled', false), 'Scheduled')
})

test('staff cards retain unknown source fields rather than filling prototype values', () => {
  const card = toStaffDirectoryCard({
    ...apiRow,
    name_en: null,
    unit_name: null,
    status: null,
    certs: [],
    scheduled_hours: Number.NaN,
    contracted_period_hours: Number.NaN,
  })

  assert.equal(card.primaryName, '陳小明')
  assert.equal(card.secondaryName, null)
  assert.equal(card.unitName, null)
  assert.equal(card.status, null)
  assert.deepEqual(card.certificates, [])
  assert.equal(card.scheduledHours, null)
  assert.equal(card.contractedPeriodHours, null)
  assert.equal(sourceHours(card.scheduledHours, 'Not provided'), 'Not provided')
})

test('staff cards retain certificate records when the summary certificate list is empty', () => {
  const card = toStaffDirectoryCard({
    ...apiRow,
    certs: [],
    certificates: [{ cert_type: 'Medication Safety' }],
  })

  assert.deepEqual(card.certificates, ['Medication Safety'])
})

test('directory filtering searches real identity fields while matching the literal backend role code', () => {
  const card = toStaffDirectoryCard(apiRow)
  assert.equal(matchesStaffDirectoryFilter(card, 'north', 'ALL'), true)
  assert.equal(matchesStaffDirectoryFilter(card, '陳小明', 'PCW'), true)
  assert.equal(matchesStaffDirectoryFilter(card, 'Chan', 'RN'), false)
})
