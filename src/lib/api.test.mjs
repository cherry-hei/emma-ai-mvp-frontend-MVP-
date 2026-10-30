import assert from 'node:assert/strict'
import test from 'node:test'

class MemoryStorage {
  values = new Map()

  getItem(key) {
    return this.values.get(key) ?? null
  }

  setItem(key, value) {
    this.values.set(key, String(value))
  }

  removeItem(key) {
    this.values.delete(key)
  }
}

function deferred() {
  let resolve
  const promise = new Promise((nextResolve) => { resolve = nextResolve })
  return { promise, resolve }
}

function session({
  accessToken,
  refreshToken,
  userId = 'user-1',
  email = 'user@example.test',
  facilityName = 'Home A',
} = {}) {
  return {
    access_token: accessToken,
    ...(refreshToken === undefined ? {} : { refresh_token: refreshToken }),
    user_id: userId,
    email,
    role: 'OWNER',
    facility_id: 'facility-1',
    facility_name: facilityName,
  }
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installBrowser(storage = new MemoryStorage()) {
  globalThis.window = { localStorage: storage }
  return storage
}

async function loadApi() {
  return import(`./api.ts?test=${Date.now()}-${Math.random()}`)
}

function restoreEnvironment(previous) {
  if (previous.preview === undefined) delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
  else process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW = previous.preview
  globalThis.fetch = previous.fetch
  globalThis.window = previous.window
}

test('integration preview blocks login and API requests before fetch or credentials leave the browser', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW = '1'
    const storage = installBrowser()
    storage.setItem('emma_token', 'stored-access-token')
    storage.setItem('emma_refresh', 'stored-refresh-token')
    let calls = 0
    globalThis.fetch = async () => {
      calls += 1
      throw new Error('fetch must not be called in integration preview')
    }

    const api = await loadApi()
    await assert.rejects(api.login('person@example.test', 'secret-password'), /Integration preview/)
    await assert.rejects(api.apiFetch('/auth/me'), /Integration preview/)
    await assert.rejects(api.downloadReportCsv('monthly'), /Integration preview/)
    assert.equal(calls, 0)
  } finally {
    restoreEnvironment(previous)
  }
})

test('a stale 401 cannot log out or replay a newly signed-in identity', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'old-access')
    storage.setItem('emma_refresh', 'old-refresh')
    storage.setItem('emma_session', JSON.stringify({ user_id: 'old-user' }))

    const oldRequest = deferred()
    const requests = []
    globalThis.fetch = async (url, options = {}) => {
      requests.push({ url: String(url), options })
      if (String(url).endsWith('/auth/login')) {
        return jsonResponse(session({
          accessToken: 'new-access', refreshToken: 'new-refresh', userId: 'new-user',
        }))
      }
      return oldRequest.promise
    }

    const api = await loadApi()
    let unauthorized = 0
    api.onUnauthorized(() => { unauthorized += 1 })
    const oldCall = api.apiFetch('/dashboard/summary')
    await new Promise((resolve) => setImmediate(resolve))
    await api.login('new@example.test', 'new-password')
    oldRequest.resolve(jsonResponse({ detail: 'expired' }, 401))

    await assert.rejects(oldCall, /expired/)
    assert.equal(storage.getItem('emma_token'), 'new-access')
    assert.equal(storage.getItem('emma_refresh'), 'new-refresh')
    assert.equal(JSON.parse(storage.getItem('emma_session')).user_id, 'new-user')
    assert.equal(unauthorized, 0)
    assert.equal(requests.filter((request) => request.url.endsWith('/auth/refresh')).length, 0)
    assert.equal(requests.filter((request) => request.url.endsWith('/dashboard/summary')).length, 1)
  } finally {
    restoreEnvironment(previous)
  }
})

test('a late refresh cannot restore credentials after logout', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'old-access')
    storage.setItem('emma_refresh', 'old-refresh')
    storage.setItem('emma_session', JSON.stringify({ user_id: 'old-user' }))

    const refreshResponse = deferred()
    const refreshStarted = deferred()
    globalThis.fetch = async (url) => {
      if (String(url).endsWith('/auth/refresh')) {
        refreshStarted.resolve()
        return refreshResponse.promise
      }
      return jsonResponse({ detail: 'expired' }, 401)
    }

    const api = await loadApi()
    const request = api.apiFetch('/dashboard/summary')
    await refreshStarted.promise
    api.logout()
    refreshResponse.resolve(jsonResponse(session({
      accessToken: 'late-access', refreshToken: 'late-refresh', userId: 'old-user',
    })))

    await assert.rejects(request, /expired/)
    assert.equal(storage.getItem('emma_token'), null)
    assert.equal(storage.getItem('emma_refresh'), null)
    assert.equal(storage.getItem('emma_session'), null)
  } finally {
    restoreEnvironment(previous)
  }
})

test('an earlier concurrent login cannot overwrite a newer login identity', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    const firstResponse = deferred()
    const secondResponse = deferred()
    let loginCount = 0
    globalThis.fetch = async () => {
      loginCount += 1
      return loginCount === 1 ? firstResponse.promise : secondResponse.promise
    }

    const api = await loadApi()
    const firstLogin = api.login('first@example.test', 'first-password')
    await new Promise((resolve) => setImmediate(resolve))
    const secondLogin = api.login('second@example.test', 'second-password')
    secondResponse.resolve(jsonResponse(session({
      accessToken: 'second-access', refreshToken: 'second-refresh', userId: 'second-user',
    })))
    await secondLogin
    firstResponse.resolve(jsonResponse(session({
      accessToken: 'first-access', refreshToken: 'first-refresh', userId: 'first-user',
    })))

    await assert.rejects(firstLogin, /superseded/)
    assert.equal(storage.getItem('emma_token'), 'second-access')
    assert.equal(storage.getItem('emma_refresh'), 'second-refresh')
    assert.equal(JSON.parse(storage.getItem('emma_session')).user_id, 'second-user')
  } finally {
    restoreEnvironment(previous)
  }
})

test('a new session replaces all credential fields instead of retaining old refresh data', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'old-access')
    storage.setItem('emma_refresh', 'old-refresh')
    storage.setItem('emma_session', JSON.stringify({
      user_id: 'old-user', email: 'old@example.test', role: 'OWNER', facility_id: 'old-facility', facility_name: 'Old Home',
    }))
    globalThis.fetch = async () => jsonResponse(session({
      accessToken: 'new-access', refreshToken: undefined, userId: 'new-user', email: null, facilityName: null,
    }))

    const api = await loadApi()
    await api.login('new@example.test', 'new-password')

    assert.equal(storage.getItem('emma_token'), 'new-access')
    assert.equal(storage.getItem('emma_refresh'), null)
    assert.deepEqual(JSON.parse(storage.getItem('emma_session')), {
      user_id: 'new-user', email: null, role: 'OWNER', facility_id: 'facility-1', facility_name: null,
    })
  } finally {
    restoreEnvironment(previous)
  }
})

test('task-assignment escort destinations use the published create and clear contract', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'scoped-access-token')
    const requests = []
    globalThis.fetch = async (url, options = {}) => {
      requests.push({ url: String(url), options })
      return jsonResponse({ id: 'task-1', shift_assignment_id: 'shift-1', task_label: 'Escort' })
    }

    const module = await loadApi()
    await module.api.createTaskAssignment({
      shift_assignment_id: 'shift-1', task_id: 'task-1', escort_location: 'CLINIC-A',
    })
    await module.api.updateTaskAssignment('task-1', { escort_location: null })

    assert.equal(requests.length, 2)
    assert.equal(requests[0].url, 'http://localhost:8000/task-assignments')
    assert.equal(requests[0].options.method, 'POST')
    assert.equal(requests[0].options.headers.get('Authorization'), 'Bearer scoped-access-token')
    assert.deepEqual(JSON.parse(requests[0].options.body), {
      shift_assignment_id: 'shift-1', task_id: 'task-1', escort_location: 'CLINIC-A',
    })
    assert.equal(requests[1].url, 'http://localhost:8000/task-assignments/task-1')
    assert.equal(requests[1].options.method, 'PATCH')
    assert.deepEqual(JSON.parse(requests[1].options.body), { escort_location: null })
  } finally {
    restoreEnvironment(previous)
  }
})
