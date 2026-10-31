import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { datesForRosterView, exactPaidMinutes, formatExactMinutes, taskDateTimes, moveRosterViewAnchor } from './roster-ui.ts'

const dates = Array.from({ length: 42 }, (_, index) => {
  const date = new Date('2026-10-26T00:00:00Z')
  date.setUTCDate(date.getUTCDate() + index)
  return date.toISOString().slice(0, 10)
})

test('weekly range includes seven actual columns across a month boundary', () => {
  assert.deepEqual(datesForRosterView(dates, '2026-10-31', 'week'), dates.slice(0, 7))
  assert.equal(datesForRosterView(dates, '2026-10-31', 'month').length, 6)
})

test('all 42 returned dates remain reachable in monthly views', () => {
  const displayed = new Set(['2026-10-26', '2026-11-01', '2026-12-01'].flatMap(date => datesForRosterView(dates, date, 'month')))
  assert.equal(displayed.size, 42)
})

test('month navigation cannot skip November when anchored on October 31', () => {
  assert.equal(moveRosterViewAnchor(dates, '2026-10-31', 'month', 1), '2026-11-01')
  assert.equal(moveRosterViewAnchor(dates, '2026-11-30', 'month', 1), '2026-12-01')
  assert.equal(moveRosterViewAnchor(dates, '2026-11-01', 'month', -1), '2026-10-26')
  assert.equal(moveRosterViewAnchor(dates, '2026-12-01', 'month', 1), '2026-12-01')
})

test('working-shift minutes require a valid exact backend value', () => {
  const cell = { date: '2026-10-28', shift_type: 'A', is_working: true, tasks: [] }
  assert.equal(exactPaidMinutes(cell, [{ shift_type: 'A', paid_minutes: 435 }]), 435)
  assert.equal(formatExactMinutes(435), '7h 15m')
  for (const value of [undefined, null, '435', NaN, -1, 435.5]) {
    assert.equal(exactPaidMinutes(cell, [{ shift_type: 'A', paid_minutes: value }]), null)
  }
  assert.equal(exactPaidMinutes({ shift_type: 'O', is_working: false }, []), 0)
})

test('task timestamps are Hong Kong offset with a true next calendar date', () => {
  assert.deepEqual(taskDateTimes('2026-10-31', '23:30', '01:15'), {
    ok: true, startAt: '2026-10-31T23:30:00+08:00', endAt: '2026-11-01T01:15:00+08:00', crossesMidnight: true,
  })
  assert.equal(taskDateTimes('2026-02-30', '09:00', '10:00').ok, false)
  assert.equal(taskDateTimes('2026-10-31', '09:00', '').ok, false)
})

test('a failed grid or stale version cannot remain editable, and unsaved notes are disabled', () => {
  const board = readFileSync(new URL('../components/roster/RealRosterBoard.tsx', import.meta.url), 'utf8')
  const modal = readFileSync(new URL('../components/modals/CreateShiftModal.tsx', import.meta.url), 'utf8')
  assert.ok(board.includes("setValidation(null); setGrid(null)"))
  assert.ok(board.includes("!loading && !error && grid?.period_id === periodId"))
  assert.ok(board.includes("grid?.version_id === currentVersion?.id"))
  assert.ok(board.includes('requestId !== versionsRequestRef.current'))
  assert.ok(modal.includes('value={row.note} disabled'))
  assert.ok(modal.includes('if (!next && !busy) onClose()'))
})

test('roster cards use the retained task-aware editor and do not expose simulated batch saves', () => {
  const board = readFileSync(new URL('../components/roster/RealRosterBoard.tsx', import.meta.url), 'utf8')
  assert.ok(board.includes('setSelectedStaffId(row.staff.id)'))
  assert.ok(board.includes('setFocusDate(iso)'))
  assert.ok(board.includes('setCreateShiftOpen(true)'))
  assert.ok(board.includes('assignmentId: cell?.assignment_id || null'))
  assert.ok(board.includes('onDeleted={({ staffName, date })'))
  assert.ok(board.includes('Batch creation needs an authenticated batch-roster API'))
  assert.ok(!board.includes('BatchCreateShiftModal'))
})
