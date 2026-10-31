import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { approvalCsv } from './approval-csv.js'

test('approval CSV preserves literal multilingual names, dates and code; protects formula text', () => {
  const result = approvalCsv([{ id: 'request-1', name: '職員一', name_en: 'Staff One', rank: 'EN', unit_name: '樓層甲', leave_type: 'SL', date_start: '2026-10-31', date_end: '2026-10-31', requested_shift_type: 'a230#', status: 'pending', reason: '=1+1', decision_note: '"note"' }], true)
  assert.ok(result.startsWith('\uFEFF'))
  assert.ok(result.includes('職員一'))
  assert.ok(result.includes('a230#'))
  assert.ok(result.includes('2026-10-31'))
  assert.ok(result.includes("'=1+1"))
  assert.ok(result.includes('""note""'))
})
test('approval page never exports staff_register and owner alone uses review decision', () => {
  const text = readFileSync(new URL('../app/approval/page.tsx', import.meta.url), 'utf8')
  assert.ok(!text.includes("downloadReportCsv('staff_register')"))
  assert.ok(text.includes("{isOwner && isPending && !request.reviewed"))
  assert.ok(text.includes('api.recommendLeaveRequest'))
})
test('settings hub links only to real existing API pages and no demo-save handler', () => {
  const text = readFileSync(new URL('../app/settings/page.tsx', import.meta.url), 'utf8')
  assert.ok(text.includes("href: '/scheduling'"))
  assert.ok(text.includes("href: '/shift-codes'"))
  assert.ok(!text.includes('DEMO_FACILITY'))
  assert.ok(!text.includes('setSaved'))
})
