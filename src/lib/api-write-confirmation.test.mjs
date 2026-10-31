import assert from 'node:assert/strict'
import test from 'node:test'
import {
  confirmCellUpsert,
  confirmDraftSave,
  confirmLeaveDecision,
  confirmLeaveRecommendation,
  confirmLeaveRevocation,
  confirmPeriodCreate,
  confirmStaffCreate,
  confirmStaffUpdate,
  readJsonBody,
} from './api-response.js'

function confirmationFailure(promiseOrCall) {
  return assert.throws(promiseOrCall, /not return a valid .*confirmation|save is not confirmed/)
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

class MemoryStorage {
  values = new Map()
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, String(value)) }
  removeItem(key) { this.values.delete(key) }
}

function deferred() {
  let resolve
  const promise = new Promise((nextResolve) => { resolve = nextResolve })
  return { promise, resolve }
}

async function loadApi() {
  return import(`./api.ts?write-confirmation-test=${Date.now()}-${Math.random()}`)
}

function restoreEnvironment(previous) {
  if (previous.preview === undefined) delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
  else process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW = previous.preview
  globalThis.fetch = previous.fetch
  globalThis.window = previous.window
}

test('generic JSON reads preserve every valid JSON value rather than forcing objects', async () => {
  assert.equal(await readJsonBody(new Response('null')), null)
  assert.equal(await readJsonBody(new Response('false')), false)
  assert.deepEqual(await readJsonBody(new Response('[]')), [])
  assert.deepEqual(await readJsonBody(new Response('{}')), {})
  assert.equal(await readJsonBody(new Response('0')), 0)
})

test('exact backend-shaped persisted rows confirm scoped staff, shift, period, and leave writes', () => {
  const newStaff = {
    id: 'staff-1', facility_id: 'facility-1', name: 'Ada Nurse', name_en: 'Ada',
    rank: 'RN', employment_type: 'full_time', primary_unit_id: 'unit-1',
    contracted_hours: 44, is_audited_for_medication: true, is_mentor: false,
    gender: 'F', status: 'active', created_at: '2026-10-31T03:00:00Z',
  }
  assert.equal(confirmStaffCreate(newStaff, {
    name: ' Ada Nurse ', name_en: ' Ada ', rank: 'RN', employment_type: 'full_time',
    primary_unit_id: 'unit-1', contracted_hours: 44, is_audited_for_medication: true,
    is_mentor: false, gender: 'F', status: 'active',
  }).id, 'staff-1')

  assert.equal(confirmStaffUpdate({ id: 'staff-1', status: 'inactive' }, 'staff-1', {
    status: 'inactive',
  }).id, 'staff-1')
  assert.equal(confirmCellUpsert({ assignment_id: 'assignment-1' }).assignment_id, 'assignment-1')

  const period = confirmPeriodCreate({
    period: {
      id: 'period-1', period_start: '2026-11-01', period_end: '2026-11-28',
      cycle_type: '28day', status: 'planning',
    },
    manual_version_id: 'version-1',
  }, {
    period_start: '2026-11-01', period_end: '2026-11-28', cycle_type: '28day', create_manual_version: true,
  })
  assert.equal(period.period.id, 'period-1')
  assert.equal(period.manual_version_id, 'version-1')

  assert.equal(confirmLeaveDecision({
    id: 'leave-1', status: 'approved', decision_note: 'Coverage checked',
  }, 'leave-1', 'approve', 'Coverage checked').status, 'approved')
  assert.equal(confirmLeaveRecommendation({
    id: 'recommendation-1', leave_request_id: 'leave-1', recommendation: 'reject', reason: 'No cover',
  }, 'leave-1', 'reject', ' No cover ').id, 'recommendation-1')
  assert.equal(confirmLeaveRevocation({
    id: 'leave-1', status: 'revoked', revoke_reason: 'Cover fell through',
  }, 'leave-1', ' Cover fell through ').status, 'revoked')
})

test('malformed or wrong-identity write bodies fail closed instead of confirming a save', () => {
  for (const malformed of [null, false, [], {}]) {
    confirmationFailure(() => confirmStaffCreate(malformed, {
      name: 'Ada', rank: 'RN', employment_type: 'full_time',
    }))
    confirmationFailure(() => confirmCellUpsert(malformed))
    confirmationFailure(() => confirmLeaveDecision(malformed, 'leave-1', 'approve', 'note'))
  }

  confirmationFailure(() => confirmStaffUpdate({ id: 'staff-other', status: 'inactive' }, 'staff-1', {
    status: 'inactive',
  }))
  confirmationFailure(() => confirmLeaveDecision({
    id: 'leave-other', status: 'approved', decision_note: 'note',
  }, 'leave-1', 'approve', 'note'))
  confirmationFailure(() => confirmLeaveRecommendation({
    id: 'recommendation-1', leave_request_id: 'leave-other', recommendation: 'approve', reason: 'reason',
  }, 'leave-1', 'approve', 'reason'))
  confirmationFailure(() => confirmLeaveRevocation({
    id: 'leave-other', status: 'revoked', revoke_reason: 'reason',
  }, 'leave-1', 'reason'))
  confirmationFailure(() => confirmPeriodCreate({
    period: {
      id: 'period-1', period_start: '2026-11-02', period_end: '2026-11-28',
      cycle_type: '28day', status: 'planning',
    },
    manual_version_id: 'version-other',
  }, {
    period_start: '2026-11-01', period_end: '2026-11-28', cycle_type: '28day', create_manual_version: true,
  }))
  confirmationFailure(() => confirmCellUpsert({ assignment_id: '' }))
})

test('the current save-draft {ok:true} body fails closed because it has no version or event identity', () => {
  confirmationFailure(() => confirmDraftSave({ ok: true }, 'version-1'))
  confirmationFailure(() => confirmDraftSave({ roster_version_id: 'version-other', status: 'draft' }, 'version-1'))
})

test('scoped API helpers expose only validated write confirmations', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    globalThis.window = { localStorage: new MemoryStorage() }
    globalThis.fetch = async (url) => {
      const path = String(url)
      if (path.endsWith('/staff')) return jsonResponse({
        id: 'staff-1', name: 'Ada', rank: 'RN', employment_type: 'full_time',
        status: 'active', is_audited_for_medication: false, is_mentor: false,
      }, 201)
      if (path.endsWith('/staff/staff-1')) return jsonResponse({ id: 'staff-1', status: 'inactive' })
      if (path.endsWith('/roster-periods')) return jsonResponse({
        period: {
          id: 'period-1', period_start: '2026-11-01', period_end: '2026-11-28',
          cycle_type: '28day', status: 'planning',
        },
        manual_version_id: 'version-1',
      }, 201)
      if (path.endsWith('/shifts')) return jsonResponse({ assignment_id: 'assignment-1' })
      if (path.endsWith('/rosters/version-1/save-draft')) return jsonResponse({ ok: true })
      if (path.endsWith('/leave-requests/leave-1')) {
        return jsonResponse({ id: 'leave-1', status: 'approved', decision_note: 'note' })
      }
      if (path.endsWith('/leave-requests/leave-1/recommendation')) {
        return jsonResponse({
          id: 'recommendation-1', leave_request_id: 'leave-1', recommendation: 'approve', reason: 'reason',
        }, 201)
      }
      if (path.endsWith('/leave-requests/leave-1/revoke')) {
        return jsonResponse({ id: 'leave-1', status: 'revoked', revoke_reason: 'reason' })
      }
      throw new Error(`Unexpected request ${path}`)
    }
    const { api } = await loadApi()
    assert.equal((await api.createStaff({ name: 'Ada', rank: 'RN', employment_type: 'full_time' })).id, 'staff-1')
    assert.equal((await api.updateStaff('staff-1', { status: 'inactive' })).status, 'inactive')
    assert.equal((await api.createPeriod({
      period_start: '2026-11-01', period_end: '2026-11-28', cycle_type: '28day', create_manual_version: true,
    })).period.id, 'period-1')
    assert.equal((await api.upsertCell({
      roster_version_id: 'version-1', staff_id: 'staff-1', date: '2026-11-01', shift_type: 'D',
    })).assignment_id, 'assignment-1')
    await assert.rejects(api.saveDraft('version-1'), /draft save confirmation.*not confirmed/)
    assert.equal((await api.decideLeaveRequest('leave-1', 'approve', 'note')).status, 'approved')
    await api.recommendLeaveRequest('leave-1', 'approve', 'reason')
    assert.equal((await api.revokeLeaveRequest('leave-1', 'reason')).status, 'revoked')
  } finally {
    restoreEnvironment(previous)
  }
})

test('valid 204 deletes remain accepted only for the credentials that issued the request', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = new MemoryStorage()
    storage.setItem('emma_token', 'old-access')
    globalThis.window = { localStorage: storage }
    const deleteResponse = deferred()
    globalThis.fetch = async (url) => {
      if (String(url).endsWith('/auth/login')) {
        return jsonResponse({
          access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer',
          user_id: 'user-2', email: 'new@example.test', role: 'OWNER', facility_id: 'facility-1', facility_name: 'Home A',
        })
      }
      return deleteResponse.promise
    }
    const module = await loadApi()
    const deleting = module.apiFetch('/shifts?roster_version_id=version-1', { method: 'DELETE' })
    await new Promise((resolve) => setImmediate(resolve))
    await module.login('new@example.test', 'password')
    deleteResponse.resolve(new Response(null, { status: 204 }))
    await assert.rejects(deleting, /superseded session/)

    globalThis.fetch = async () => new Response(null, { status: 204 })
    await assert.doesNotReject(module.apiFetch('/shifts?roster_version_id=version-1', { method: 'DELETE' }))
  } finally {
    restoreEnvironment(previous)
  }
})
