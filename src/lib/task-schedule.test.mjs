import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import {
  hongKongHHMM,
  hydrateTaskTimingRows,
  persistTaskTimings,
} from './task-schedule.ts'

const clock = (row) => ({
  ok: true,
  startAt: `2026-10-31T${row.start}:00+08:00`,
  endAt: `2026-10-31T${row.end}:00+08:00`,
})

test('partial task-time failure retains task 1, retries only task 2, and does not complete early', async () => {
  const initialRows = [
    { id: 'one', taskId: 'task-1', taskLabel: 'Medication', start: '09:00', end: '10:00', timingStatus: 'idle' },
    { id: 'two', taskId: 'task-2', taskLabel: 'Escort', start: '10:00', end: '11:00', timingStatus: 'idle' },
  ]
  const attemptedTaskIds = []
  let failTaskTwo = true
  const upsert = async (body) => {
    attemptedTaskIds.push(body.task_id)
    if (body.task_id === 'task-2' && failTaskTwo) throw new Error('time overlaps another assignment')
  }

  const first = await persistTaskTimings({
    shiftAssignmentId: 'shift-assignment-1', rows: initialRows, timeFor: clock, upsert,
  })

  assert.deepEqual(attemptedTaskIds, ['task-1', 'task-2'])
  assert.equal(first.complete, false, 'the UI must not emit overall saved/close after a task failure')
  assert.equal(first.rows[0].timingStatus, 'saved')
  assert.equal(first.rows[1].timingStatus, 'failed')
  assert.match(first.rows[1].timingError, /overlaps/)

  failTaskTwo = false
  const retry = await persistTaskTimings({
    shiftAssignmentId: 'shift-assignment-1', rows: first.rows, timeFor: clock, upsert,
  })

  assert.deepEqual(attemptedTaskIds, ['task-1', 'task-2', 'task-2'], 'retry must not rewrite task 1')
  assert.equal(retry.complete, true)
  assert.equal(retry.rows[0].timingStatus, 'saved')
  assert.equal(retry.rows[1].timingStatus, 'saved')
})

test('editing a previously saved row resets it to pending and upserts its changed clock', async () => {
  const calls = []
  const changed = {
    id: 'one', taskId: 'task-1', taskLabel: 'Medication',
    start: '09:30', end: '10:30', timingStatus: 'idle',
  }

  const result = await persistTaskTimings({
    shiftAssignmentId: 'shift-assignment-1', rows: [changed], timeFor: clock,
    upsert: async (body) => { calls.push(body) },
  })

  assert.equal(result.complete, true)
  assert.equal(result.rows[0].timingStatus, 'saved')
  assert.deepEqual(calls, [{
    shift_assignment_id: 'shift-assignment-1', task_id: 'task-1',
    start_at: '2026-10-31T09:30:00+08:00', end_at: '2026-10-31T10:30:00+08:00',
  }])
})

test('partial retry saves a new entered row without rewriting an already-saved row', async () => {
  const calls = []
  const rows = [
    { id: 'one', taskId: 'task-1', taskLabel: 'Medication', start: '09:00', end: '10:00', timingStatus: 'saved' },
    { id: 'two', taskId: 'task-2', taskLabel: 'Escort', start: '10:00', end: '11:00', timingStatus: 'failed', timingError: 'temporary failure' },
    { id: 'three', taskId: 'task-3', taskLabel: 'Meals', start: '11:00', end: '12:00', timingStatus: 'idle' },
  ]

  const result = await persistTaskTimings({
    shiftAssignmentId: 'shift-assignment-1', rows, timeFor: clock,
    upsert: async (body) => { calls.push(body.task_id) },
  })

  assert.deepEqual(calls, ['task-2', 'task-3'])
  assert.equal(result.complete, true)
  assert.deepEqual(result.rows.map((row) => row.timingStatus), ['saved', 'saved', 'saved'])
})

test('reopened label-only tasks remain idle advisory rows while persisted timestamps hydrate in Hong Kong time', () => {
  const rows = hydrateTaskTimingRows(
    ['Medication', 'Escort'],
    [
      { id: 'task-1', label: 'Medication' },
      { id: 'task-2', label: 'Escort' },
    ],
    [
      {
        id: 'persisted-1', task_id: 'task-1', task_label: 'Medication',
        start_at: '2026-10-31T01:15:00Z', end_at: '2026-10-31T02:45:00Z',
      },
      {
        id: 'persisted-2', task_id: 'task-2', task_label: 'Escort',
        start_at: null, end_at: null,
      },
    ],
  )

  assert.equal(hongKongHHMM('2026-10-31T01:15:00Z'), '09:15')
  assert.deepEqual(rows.map((row) => ({ label: row.taskLabel, start: row.start, end: row.end, status: row.timingStatus })), [
    { label: 'Medication', start: '09:15', end: '10:45', status: 'saved' },
    { label: 'Escort', start: '', end: '', status: 'idle' },
  ])
  assert.match(rows[1].timingAdvisory, /not saved/i)
  assert.equal(rows[1].taskIdentityLocked, true)
})

test('an empty new row is advisory only and cannot block completion or create a false task failure', async () => {
  const result = await persistTaskTimings({
    shiftAssignmentId: 'shift-assignment-1',
    rows: [{ id: 'empty', taskId: '', taskLabel: '', start: '', end: '', timingStatus: 'idle' }],
    timeFor: clock,
    upsert: async () => { throw new Error('must not be called') },
  })

  assert.equal(result.complete, true)
  assert.equal(result.attempted, 0)
  assert.equal(result.failed, 0)
  assert.equal(result.rows[0].timingStatus, 'idle')
})

test('CreateShiftModal uses the recovery helper rather than a separate task-time save loop', () => {
  const modal = readFileSync(new URL('../components/modals/CreateShiftModal.tsx', import.meta.url), 'utf8')
  assert.match(modal, /from '@\/lib\/task-schedule'/)
  assert.match(modal, /persistTaskTimings\(/)
  assert.doesNotMatch(modal, /onlyFailed:/)
  assert.match(modal, /timingStatus: 'idle', timingError: undefined, timingAdvisory: undefined/)
  assert.match(modal, /disabled=\{busy \|\| row\.taskIdentityLocked\}/)
  assert.match(modal, /availableTasks\.length === 0 && !manualMode && rows\.length === 0/)
  assert.match(modal, /!next && !busy && !hasFailedTiming/)
})
