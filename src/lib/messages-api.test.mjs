import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync, rmSync, writeFileSync } from 'node:fs'

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

async function loadMessagesApi() {
  // The app's TypeScript/bundler convention is extensionless (`./api`). Node's
  // strip-types runner does not resolve that specifier, so materialise a
  // byte-for-byte test copy with only this import made explicit. The production
  // source remains on the project's normal Next.js resolution path.
  const testPath = new URL(`./.messages-api-node-test-${process.pid}-${Date.now()}-${Math.random()}.ts`, import.meta.url)
  const sourcePath = new URL('./messages-api.ts', import.meta.url)
  writeFileSync(testPath, readFileSync(sourcePath, 'utf8').replace("from './api'", "from './api.ts'"))
  try {
    return await import(`${testPath.href}?test=${Date.now()}-${Math.random()}`)
  } finally {
    rmSync(testPath, { force: true })
  }
}

function restoreEnvironment(previous) {
  if (previous.preview === undefined) delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
  else process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW = previous.preview
  globalThis.fetch = previous.fetch
  globalThis.window = previous.window
}

test('proposed messages client uses only provisioned profile IDs and facility JWT requests', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'facility-scoped-token')
    const requests = []
    globalThis.fetch = async (url, options = {}) => {
      requests.push({ url: String(url), options })
      if (String(url).endsWith('/messages/contacts')) {
        return jsonResponse([
          { id: 'profile-1', display_name: 'Provisioned Nurse', role: 'RN', staff_id: 'staff-1' },
        ])
      }
      if (String(url).endsWith('/messages')) {
        if (options.method === 'POST') {
          return jsonResponse({
            id: 'message-1', sender_profile_id: 'manager-profile', recipient_profile_id: 'profile-1',
            body: 'Confirmed message', created_at: '2026-10-31T03:15:00Z', read_at: null,
          })
        }
        return jsonResponse([])
      }
      if (String(url).endsWith('/messages/message%2F1/read')) {
        return jsonResponse({
          id: 'message/1', sender_profile_id: 'profile-1', recipient_profile_id: 'manager-profile',
          body: 'Incoming message', created_at: '2026-10-31T03:14:00Z', read_at: '2026-10-31T03:16:00Z',
        })
      }
      throw new Error(`Unexpected request ${url}`)
    }

    const { messagesApi } = await loadMessagesApi()
    const contacts = await messagesApi.contacts()
    const sent = await messagesApi.send('profile-1', 'Confirmed message')
    await messagesApi.markRead('message/1')

    assert.deepEqual(contacts, [{ id: 'profile-1', display_name: 'Provisioned Nurse', role: 'RN', staff_id: 'staff-1' }])
    assert.equal(sent.id, 'message-1')
    assert.equal(requests.length, 3)
    assert.equal(requests[0].url, 'http://localhost:8000/messages/contacts')
    assert.equal(requests[0].options.headers.get('Authorization'), 'Bearer facility-scoped-token')
    assert.equal(requests[1].url, 'http://localhost:8000/messages')
    assert.equal(requests[1].options.method, 'POST')
    assert.deepEqual(JSON.parse(requests[1].options.body), {
      recipient_profile_id: 'profile-1', body: 'Confirmed message',
    })
    assert.equal(requests[2].url, 'http://localhost:8000/messages/message%2F1/read')
    assert.equal(requests[2].options.method, 'PATCH')
  } finally {
    restoreEnvironment(previous)
  }
})

test('empty or malformed write confirmations are failures, never successful sends or reads', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'facility-scoped-token')
    globalThis.fetch = async () => jsonResponse({})

    const { messagesApi } = await loadMessagesApi()
    await assert.rejects(messagesApi.send('profile-1', 'Do not clear this draft'), /valid send confirmation/)
    await assert.rejects(messagesApi.markRead('message-1'), /valid read confirmation/)
  } finally {
    restoreEnvironment(previous)
  }
})

test('malformed provisioned-contact or conversation entries fail closed', async () => {
  const previous = {
    preview: process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW,
    fetch: globalThis.fetch,
    window: globalThis.window,
  }
  try {
    delete process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW
    const storage = installBrowser()
    storage.setItem('emma_token', 'facility-scoped-token')
    globalThis.fetch = async (url) => jsonResponse(String(url).endsWith('/messages/contacts')
      ? [{ id: '', display_name: 'Not a provisioned profile', role: 'RN' }]
      : [{ id: 'message-1', sender_profile_id: 'profile-1', recipient_profile_id: '', body: 'Broken', created_at: '2026-10-31T03:15:00Z', read_at: null }])

    const { messagesApi } = await loadMessagesApi()
    await assert.rejects(messagesApi.contacts(), /invalid contacts response/)
    await assert.rejects(messagesApi.list(), /invalid conversation response/)
  } finally {
    restoreEnvironment(previous)
  }
})

test('messages page has no demo storage, synthetic replies, staff directory call, or obsolete regional gate', () => {
  const page = readFileSync(new URL('../app/messages/page.tsx', import.meta.url), 'utf8')

  assert.match(page, /messagesApi\.contacts\(\)/)
  assert.match(page, /messagesApi\.list\(\)/)
  assert.match(page, /messagesApi\.send\(contactId, body\)/)
  assert.match(page, /requestGeneration/)
  assert.match(page, /contentGeneration/)
  assert.match(page, /draftsByContact/)
  assert.doesNotMatch(page, /localStorage|DEMO_STAFF|setTimeout|listStaff|\/staff/)
  assert.doesNotMatch(page, /Hong Kong|香港|zh-HK|synthetic/i)
})
