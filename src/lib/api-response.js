/** A successful HTTP status alone is not proof of a successful data write. */
export async function readJsonBody(response) {
  const text = await response.text()
  if (!text.trim()) throw new Error('The server returned an empty response. The result or save is not confirmed; please reload to verify.')
  try { return JSON.parse(text) }
  catch { throw new Error('The server returned an incomplete or invalid response. The result or save is not confirmed; please reload to verify.') }
}

function confirmationError(operation) {
  return new Error(`The server did not return a valid ${operation} confirmation. The save is not confirmed; please reload to verify.`)
}

function recordFrom(value, operation) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw confirmationError(operation)
  return value
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function requireNonEmptyString(record, key, operation) {
  if (!nonEmptyString(record[key])) throw confirmationError(operation)
  return record[key]
}

function requireExact(record, key, expected, operation) {
  if (!Object.prototype.hasOwnProperty.call(record, key) || !Object.is(record[key], expected)) {
    throw confirmationError(operation)
  }
}

function confirmRequestedFields(record, requested, operation, normalise = (key, value) => value) {
  for (const [key, value] of Object.entries(requested)) {
    // JSON.stringify omits undefined keys, so they were never part of this write.
    if (value !== undefined) requireExact(record, key, normalise(key, value), operation)
  }
}

/** The raw row returned by POST /staff must identify and reflect the requested staff record. */
export function confirmStaffCreate(value, requested) {
  const operation = 'staff create'
  const row = recordFrom(value, operation)
  requireNonEmptyString(row, 'id', operation)
  confirmRequestedFields(row, requested, operation, (key, field) => {
    // The service trims both create names before storing them.
    return (key === 'name' || key === 'name_en') && typeof field === 'string' ? field.trim() : field
  })
  requireExact(row, 'status', requested.status ?? 'active', operation)
  requireExact(row, 'is_audited_for_medication', requested.is_audited_for_medication ?? false, operation)
  requireExact(row, 'is_mentor', requested.is_mentor ?? false, operation)
  return row
}

/** The raw row returned by PATCH /staff/{id} must be that row and include every sent patch. */
export function confirmStaffUpdate(value, staffId, patch) {
  const operation = 'staff update'
  const row = recordFrom(value, operation)
  requireExact(row, 'id', staffId, operation)
  confirmRequestedFields(row, patch, operation, (key, field) => {
    // The update service trims `name`; `name_en` is otherwise persisted as sent.
    return key === 'name' && typeof field === 'string' ? field.trim() : field
  })
  return row
}

/** POST/PATCH /shifts returns only the durable assignment ID. */
export function confirmCellUpsert(value) {
  const operation = 'shift assignment'
  const row = recordFrom(value, operation)
  requireNonEmptyString(row, 'assignment_id', operation)
  return row
}

/** POST /roster-periods returns a period plus the requested manual-version ID. */
export function confirmPeriodCreate(value, requested) {
  const operation = 'roster period create'
  const response = recordFrom(value, operation)
  const period = recordFrom(response.period, operation)
  requireNonEmptyString(period, 'id', operation)
  requireExact(period, 'period_start', requested.period_start, operation)
  requireExact(period, 'period_end', requested.period_end, operation)
  requireExact(period, 'cycle_type', requested.cycle_type ?? '28day', operation)
  requireExact(period, 'status', 'planning', operation)

  if (requested.create_manual_version === false) {
    requireExact(response, 'manual_version_id', null, operation)
  } else {
    requireNonEmptyString(response, 'manual_version_id', operation)
  }
  return response
}

/** PATCH /leave-requests/{id} returns the persisted request row with its final status. */
export function confirmLeaveDecision(value, requestId, decision, note) {
  const operation = 'leave decision'
  const row = recordFrom(value, operation)
  const expectedStatus = {
    approve: 'approved',
    reject: 'rejected',
    review: 'reviewed',
  }[decision]
  requireExact(row, 'id', requestId, operation)
  requireExact(row, 'status', expectedStatus, operation)
  // `review` deliberately does not persist a note; final decisions do.
  if (decision !== 'review') requireExact(row, 'decision_note', note ?? null, operation)
  return row
}

/** POST /recommendation returns the persisted reviewer row, not a generic success object. */
export function confirmLeaveRecommendation(value, requestId, recommendation, reason) {
  const operation = 'leave recommendation'
  const row = recordFrom(value, operation)
  requireNonEmptyString(row, 'id', operation)
  requireExact(row, 'leave_request_id', requestId, operation)
  requireExact(row, 'recommendation', recommendation, operation)
  requireExact(row, 'reason', reason.trim(), operation)
  return row
}

/** POST /revoke returns the request row after its approval has been revoked. */
export function confirmLeaveRevocation(value, requestId, reason) {
  const operation = 'leave revocation'
  const row = recordFrom(value, operation)
  requireExact(row, 'id', requestId, operation)
  requireExact(row, 'status', 'revoked', operation)
  requireExact(row, 'revoke_reason', reason.trim(), operation)
  return row
}

/**
 * The deployed route returns only `{ ok: true }`, although the service writes a
 * roster_publish_events row. That body does not identify the version or expose
 * a durable event ID, and no scoped read contract can verify the event. Fail
 * closed until the API returns a version/event confirmation.
 */
export function confirmDraftSave(_value, _versionId) {
  throw confirmationError('draft save')
}
