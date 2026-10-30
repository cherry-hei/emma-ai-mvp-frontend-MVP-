import assert from 'node:assert/strict'
import test from 'node:test'
import type { RosterCell, ShiftDef } from './apiTypes'
import {
  datesForRosterView,
  exactPaidMinutes,
  formatExactMinutes,
  taskDateTimes,
} from './roster-ui'

const dates = [
  '2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29',
  '2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02',
]

test('datesForRosterView limits weekly and monthly displays to roster-returned dates', () => {
  assert.deepEqual(datesForRosterView(dates, '2026-10-28', 'week'), dates.slice(0, 7))
  assert.deepEqual(datesForRosterView(dates, '2026-10-28', 'month'), dates.slice(0, 6))
  assert.deepEqual(datesForRosterView(dates, 'not-a-date', 'staff'), dates.slice(0, 7))
})

test('datesForRosterView preserves every API-returned date across a 42-day NAAC period', () => {
  const start = new Date(Date.UTC(2026, 9, 26))
  const period = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(start)
    day.setUTCDate(day.getUTCDate() + index)
    return day.toISOString().slice(0, 10)
  })

  const viewed = new Set([
    ...datesForRosterView(period, period[0], 'month'),
    ...datesForRosterView(period, '2026-11-15', 'month'),
    ...datesForRosterView(period, period[period.length - 1], 'month'),
  ])
  assert.equal(viewed.size, 42)
  assert.deepEqual([...viewed].sort(), period)
})

test('exactPaidMinutes accepts only an explicit valid backend value', () => {
  const working: RosterCell = { date: '2026-10-28', shift_type: 'AN', is_working: true, tasks: [] }
  const off: RosterCell = { date: '2026-10-28', shift_type: 'OFF', is_working: false, tasks: [] }
  const defs: ShiftDef[] = [
    { id: 'an', shift_type: 'AN', is_working: true, cross_midnight: true, paid_minutes: 960 },
    { id: 'off', shift_type: 'OFF', is_working: false, cross_midnight: false, paid_minutes: 480 },
  ]

  assert.equal(exactPaidMinutes(working, defs), 960)
  assert.equal(exactPaidMinutes(off, defs), 0)
  assert.equal(exactPaidMinutes(working, [{ ...defs[0], paid_minutes: null }]), null)
  assert.equal(formatExactMinutes(960), '16h 00m')
})

test('taskDateTimes preserves Hong Kong time and rolls an overnight task forward', () => {
  assert.deepEqual(taskDateTimes('2026-10-31', '23:30', '01:15'), {
    ok: true,
    startAt: '2026-10-31T23:30:00+08:00',
    endAt: '2026-11-01T01:15:00+08:00',
    crossesMidnight: true,
  })
  assert.deepEqual(taskDateTimes('2026-02-30', '09:00', '10:00'), { ok: false, error: 'invalid_date' })
  assert.deepEqual(taskDateTimes('2026-10-31', '09:00', ''), { ok: false, error: 'incomplete_time' })
})
