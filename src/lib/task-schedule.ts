export type TaskTimingStatus = 'idle' | 'saved' | 'failed'

/** A modal task row, with durable per-time save state. */
export type TaskTimingRow = {
  id: string
  taskId: string
  taskLabel: string
  start: string
  end: string
  timingStatus: TaskTimingStatus
  timingError?: string
  /** A valid label-only task has no schedule to retry, but merits an explanation. */
  timingAdvisory?: string
  /** Prevent task-label changes when the row already represents a saved cell task. */
  taskIdentityLocked?: boolean
}

export type TaskTimingDefinition = { id: string; label: string }
export type PersistedTaskTiming = {
  id: string
  task_id?: string | null
  task_label: string
  start_at?: string | null
  end_at?: string | null
}

export type TaskTimingInput =
  | { ok: true; startAt?: undefined; endAt?: undefined }
  | { ok: true; startAt: string; endAt: string }
  | { ok: false; error: string }

export type TaskTimingUpsert = (body: {
  shift_assignment_id: string
  task_id: string
  start_at: string
  end_at: string
}) => Promise<unknown>

const MISSING_SAVED_TIME = 'Task time is not saved. Enter both times and retry.'

function matchingDefinition(
  taskLabel: string,
  taskId: string | null | undefined,
  definitions: TaskTimingDefinition[],
): TaskTimingDefinition | undefined {
  return definitions.find((definition) => definition.id === taskId)
    ?? definitions.find((definition) => definition.label === taskLabel)
}

/**
 * Converts an API DateTime to the displayed local Hong Kong wall-clock time.
 * It deliberately returns an empty value for an absent or malformed timestamp:
 * callers must show the persisted schedule as incomplete rather than guess it.
 */
export function hongKongHHMM(value?: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (!Number.isFinite(parsed.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Hong_Kong',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(parsed)
  const hour = parts.find((part) => part.type === 'hour')?.value
  const minute = parts.find((part) => part.type === 'minute')?.value
  return hour && minute ? `${hour}:${minute}` : ''
}

/**
 * Combines legacy cell task labels with the task-assignment records that own
 * timestamps. A label without a valid persisted pair is a valid label-only
 * task, not evidence of a failed timing write. It stays idle with an advisory;
 * only a write that fails in this modal's current session becomes failed.
 */
export function hydrateTaskTimingRows(
  taskLabels: string[],
  definitions: TaskTimingDefinition[],
  assignments: PersistedTaskTiming[],
): TaskTimingRow[] {
  const rows: TaskTimingRow[] = []
  const claimedAssignmentIds = new Set<string>()

  const addAssignment = (assignment: PersistedTaskTiming, fallbackLabel?: string) => {
    const definition = matchingDefinition(assignment.task_label || fallbackLabel || '', assignment.task_id, definitions)
    const start = hongKongHHMM(assignment.start_at)
    const end = hongKongHHMM(assignment.end_at)
    const complete = !!start && !!end
    rows.push({
      id: `task-assignment-${assignment.id}`,
      taskId: assignment.task_id || definition?.id || '',
      taskLabel: assignment.task_label || fallbackLabel || definition?.label || 'Unknown task',
      start,
      end,
      timingStatus: complete ? 'saved' : 'idle',
      timingError: undefined,
      timingAdvisory: complete ? undefined : MISSING_SAVED_TIME,
      taskIdentityLocked: true,
    })
    claimedAssignmentIds.add(assignment.id)
  }

  taskLabels.forEach((label, index) => {
    const definition = matchingDefinition(label, undefined, definitions)
    const assignment = assignments.find((item) => !claimedAssignmentIds.has(item.id) && (
      (!!item.task_id && item.task_id === definition?.id) || item.task_label === label
    ))
    if (assignment) {
      addAssignment(assignment, label)
      return
    }
    rows.push({
      id: `task-label-${index}-${label}`,
      taskId: definition?.id || '',
      taskLabel: label || definition?.label || 'Unknown task',
      start: '',
      end: '',
      timingStatus: 'idle',
      timingAdvisory: MISSING_SAVED_TIME,
      taskIdentityLocked: true,
    })
  })

  assignments.forEach((assignment) => {
    if (!claimedAssignmentIds.has(assignment.id)) addAssignment(assignment)
  })

  return rows
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : 'Task time could not be saved.'
}

/**
 * Upserts every unsaved row with a complete entered time. This deliberately has
 * no roster-cell write: retrying a failed task cannot overwrite the cell or
 * conceal another failed task. Rows without any entered time remain idle; they
 * are ordinary label-only tasks (including a blank newly-added row), not a
 * claimed timed schedule. Saved rows are the only rows never rewritten.
 */
export async function persistTaskTimings(input: {
  shiftAssignmentId: string
  rows: TaskTimingRow[]
  timeFor: (row: TaskTimingRow) => TaskTimingInput
  upsert: TaskTimingUpsert
}): Promise<{ rows: TaskTimingRow[]; attempted: number; saved: number; failed: number; complete: boolean }> {
  let attempted = 0
  let saved = 0
  let failed = 0
  const next: TaskTimingRow[] = []

  for (const row of input.rows) {
    if (row.timingStatus === 'saved') {
      next.push(row)
      continue
    }
    // New rows begin with the shift's suggested hours but no selected task.
    // They do not represent a requested task time and must not block saving.
    if (!row.taskId && !row.taskLabel) {
      next.push(row)
      continue
    }

    const timing = input.timeFor(row)
    if (!timing.ok) {
      failed += 1
      next.push({ ...row, timingStatus: 'failed', timingError: timing.error })
      continue
    }
    if (!timing.startAt || !timing.endAt) {
      if (row.timingStatus === 'failed') {
        failed += 1
        next.push({ ...row, timingError: row.timingError || MISSING_SAVED_TIME })
      } else {
        next.push(row)
      }
      continue
    }
    if (!row.taskId) {
      failed += 1
      next.push({ ...row, timingStatus: 'failed', timingError: 'Task definition is unavailable; this task time cannot be retried.', timingAdvisory: undefined })
      continue
    }

    attempted += 1
    try {
      await input.upsert({
        shift_assignment_id: input.shiftAssignmentId,
        task_id: row.taskId,
        start_at: timing.startAt,
        end_at: timing.endAt,
      })
      saved += 1
      next.push({ ...row, timingStatus: 'saved', timingError: undefined, timingAdvisory: undefined, taskIdentityLocked: true })
    } catch (error) {
      failed += 1
      next.push({ ...row, timingStatus: 'failed', timingError: errorMessage(error), timingAdvisory: undefined, taskIdentityLocked: true })
    }
  }

  return {
    rows: next,
    attempted,
    saved,
    failed,
    complete: next.every((row) => row.timingStatus !== 'failed'),
  }
}
