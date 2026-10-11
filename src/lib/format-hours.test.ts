import assert from 'node:assert/strict'
import test from 'node:test'
import { formatHoursMinutes } from './format-hours'

test('formatHoursMinutes renders persisted minutes as hours and minutes', () => {
  assert.equal(formatHoursMinutes(435), '7h15m')
  assert.equal(formatHoursMinutes(435, 'zh'), '7小時15分')
  assert.equal(formatHoursMinutes(0), '0h00m')
})

test('formatHoursMinutes keeps unknown values distinct from zero', () => {
  assert.equal(formatHoursMinutes(null), '—')
  assert.equal(formatHoursMinutes(undefined, 'zh'), '—')
  assert.equal(formatHoursMinutes(Number.NaN), '—')
  assert.equal(formatHoursMinutes(-1), '—')
})
