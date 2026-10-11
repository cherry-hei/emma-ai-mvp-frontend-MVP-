import assert from 'node:assert/strict'
import test from 'node:test'
import { taskDateTimes } from './roster-ui'

/** Reusable fixtures for modal/API mocks: no browser, network, or database required. */
export const taskDateTimeFixtures = [
  {
    name: 'same-day task uses an explicit Hong Kong offset',
    date: '2026-10-11', start: '09:15', end: '10:45',
    expected: {
      ok: true as const,
      startAt: '2026-10-11T09:15:00+08:00',
      endAt: '2026-10-11T10:45:00+08:00',
      crossesMidnight: false,
    },
  },
  {
    name: 'earlier end rolls the task to the next UTC calendar day',
    date: '2026-10-11', start: '23:30', end: '01:15',
    expected: {
      ok: true as const,
      startAt: '2026-10-11T23:30:00+08:00',
      endAt: '2026-10-12T01:15:00+08:00',
      crossesMidnight: true,
    },
  },
  {
    name: 'equal times are explicitly next-day rather than a zero duration',
    date: '2026-10-31', start: '08:00', end: '08:00',
    expected: {
      ok: true as const,
      startAt: '2026-10-31T08:00:00+08:00',
      endAt: '2026-11-01T08:00:00+08:00',
      crossesMidnight: true,
    },
  },
] as const

test('taskDateTimes returns reusable modal fixtures', () => {
  for (const fixture of taskDateTimeFixtures) {
    assert.deepEqual(taskDateTimes(fixture.date, fixture.start, fixture.end), fixture.expected, fixture.name)
  }
})

test('taskDateTimes permits a wholly blank optional timing only', () => {
  assert.deepEqual(taskDateTimes('2026-10-11', '', ''), { ok: true, crossesMidnight: false })
  assert.deepEqual(taskDateTimes('2026-10-11', '09:00', ''), { ok: false, error: 'incomplete_time' })
})

test('taskDateTimes rejects impossible dates and non-HH:mm values', () => {
  assert.deepEqual(taskDateTimes('2026-02-30', '09:00', '10:00'), { ok: false, error: 'invalid_date' })
  assert.deepEqual(taskDateTimes('2026-10-11', '9:00', '10:00'), { ok: false, error: 'invalid_time' })
})
