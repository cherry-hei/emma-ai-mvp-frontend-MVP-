import test from 'node:test'
import assert from 'node:assert/strict'
import { isoAddDays, weekStart, moveWindow, windowDates } from '../src/lib/rosterWindow.ts'

const cycle = Array.from({ length: 42 }, (_, i) => isoAddDays('2026-10-01', i))

test('Hong Kong dates do not drift on Sunday, October boundary or leap day', () => {
  assert.equal(weekStart('2026-10-01'), '2026-09-28')
  assert.equal(weekStart('2026-10-04'), '2026-09-28')
  assert.equal(isoAddDays('2028-02-28', 1), '2028-02-29')
  assert.equal(isoAddDays('2026-10-31', 1), '2026-11-01')
})

test('all-staff week, all-staff month and one staff use the same period dates', () => {
  assert.deepEqual(windowDates(cycle, 'WEEK_ALL', '2026-10-01'), cycle.slice(0, 4))
  assert.deepEqual(windowDates(cycle, 'STAFF', '2026-10-05'), cycle.slice(4, 11))
  assert.equal(windowDates(cycle, 'MONTH_ALL', '2026-10-01').length, 31)
  assert.equal(windowDates(cycle, 'MONTH_ALL', '2026-11-01').length, 11)
  assert.equal(windowDates(cycle, 'WEEK_ALL', '2026-11-09').length, 3)
  assert.deepEqual(windowDates(cycle, 'MONTH_ALL', '2026-12-01'), [])
})

test('window navigation is calendar-aware and does not invent roster cells', () => {
  assert.equal(moveWindow('2026-10-01', 'MONTH_ALL', 1), '2026-11-01')
  assert.equal(moveWindow('2026-10-29', 'STAFF', 1), '2026-11-05')
  assert.equal(moveWindow('2026-11-01', 'MONTH_ALL', -1), '2026-10-01')
})
