import assert from 'node:assert/strict'
import test from 'node:test'

const preferences = await import('./display-preferences.ts')
const {
  DISPLAY_PREFERENCES_STORAGE_KEY,
  VIEW_POSITIONS_STORAGE_KEY,
  clampTextScale,
  normalizePathname,
  readDisplayTextScale,
  readPageViewPosition,
  saveDisplayTextScale,
  savePageViewPosition,
} = preferences

class MemoryStorage {
  values = new Map()

  getItem(key) {
    return this.values.get(key) ?? null
  }

  setItem(key, value) {
    this.values.set(key, value)
  }
}

test('supported text scales clamp malformed values safely', () => {
  assert.equal(clampTextScale(100), 100)
  assert.equal(clampTextScale(126), 125)
  assert.equal(clampTextScale(151), 150)
  assert.equal(clampTextScale(999), 200)
  assert.equal(clampTextScale('not-a-number'), 100)

  const storage = new MemoryStorage()
  storage.setItem(DISPLAY_PREFERENCES_STORAGE_KEY, JSON.stringify({ textScale: 999 }))
  assert.equal(readDisplayTextScale(storage), 200)
  assert.equal(saveDisplayTextScale(149, storage), 150)
  assert.deepEqual(JSON.parse(storage.getItem(DISPLAY_PREFERENCES_STORAGE_KEY)), { textScale: 150 })
})

test('storage failures never prevent a usable display preference', () => {
  const unavailable = {
    getItem() { throw new Error('Storage unavailable') },
    setItem() { throw new Error('Storage unavailable') },
  }

  assert.equal(readDisplayTextScale(unavailable), 100)
  assert.equal(saveDisplayTextScale(200, unavailable), 200)
  assert.doesNotThrow(() => savePageViewPosition('/roster', { top: 20, left: 0 }, unavailable))
})

test('route-specific positions retain only numeric UI coordinates', () => {
  const storage = new MemoryStorage()
  savePageViewPosition('/roster?period=current', { top: 420, left: 75 }, storage)
  savePageViewPosition('/reports', { top: 80, left: 0 }, storage)

  assert.deepEqual(readPageViewPosition('/roster', storage), { top: 420, left: 75 })
  assert.deepEqual(readPageViewPosition('/reports', storage), { top: 80, left: 0 })

  savePageViewPosition('/invalid', { top: Number.NaN, left: 0 }, storage)
  assert.equal(readPageViewPosition('/invalid', storage), null)
  assert.ok(storage.getItem(VIEW_POSITIONS_STORAGE_KEY))
})

test('pathnames reject unsafe values and discard query strings', () => {
  assert.equal(normalizePathname('/staff?tab=history'), '/staff')
  assert.equal(normalizePathname('staff'), null)
  assert.equal(normalizePathname('/a path'), null)
  assert.equal(normalizePathname('/'), '/')
})
