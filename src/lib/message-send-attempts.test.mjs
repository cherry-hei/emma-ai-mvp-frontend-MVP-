import assert from 'node:assert/strict'
import test from 'node:test'
import { MessageSendAttempts } from './message-send-attempts.ts'

function attempts() {
  let sequence = 0
  return new MessageSendAttempts(() => `key-${++sequence}`)
}

test('an unchanged failed send retries the same contact/body/key', () => {
  const pending = attempts()
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-1')
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-1')
  assert.equal(pending.keyFor('peer-b', 'Hello'), 'key-2')
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-1')
})

test('editing or a durable confirmation retires the previous send intent', () => {
  const pending = attempts()
  pending.keyFor('peer-a', 'Hello')
  pending.discardIfChanged('peer-a', 'Edited')
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-2')
  pending.confirmed('peer-a')
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-3')
})

test('logout or tenant reset cannot reuse another identity retry key', () => {
  const pending = attempts()
  pending.keyFor('peer-a', 'Hello')
  pending.reset()
  assert.equal(pending.keyFor('peer-a', 'Hello'), 'key-2')
})
