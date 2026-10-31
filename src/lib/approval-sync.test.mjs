import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { readJsonBody } from './api-response.js'
const page = readFileSync(new URL('../app/approval/page.tsx', import.meta.url), 'utf8')
const client = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')
test('valid JSON including explicit zero is preserved', async () => {
  assert.deepEqual(await readJsonBody(new Response('{"total":0}')), {total:0})
})
test('empty and interrupted 200 results are not accepted as saved', async () => {
  await assert.rejects(readJsonBody(new Response('')), /not confirmed/)
  await assert.rejects(readJsonBody(new Response('{"ok":')), /not confirmed/)
})
test('non-JSON errors never expose an HTML response as a successful write', async () => {
  await assert.rejects(readJsonBody(new Response('<html>failure</html>')), /invalid response/)
})
test('recommendation uses the dedicated endpoint and required reason, never PATCH review', () => {
  assert.match(client, /recommendLeaveRequest:[\s\S]*?\/recommendation[\s\S]*?method: 'POST'/)
  assert.match(page, /await api\.recommendLeaveRequest\(id/)
  assert.doesNotMatch(page, /recommend_approve.*return 'review'/)
  assert.match(page, /推薦理由必填/)
})
test('dialog reasons survive failed saves and responses are scoped to identity and filters', () => {
  assert.match(page, /if \(saved\) setShowRejectModal\(false\)/)
  assert.match(page, /if \(saved\) setShowRecommendModal\(false\)/)
  assert.match(page, /generation !== loads\.current/)
  assert.match(page, /originatingScope !== activeScope\.current/)
  assert.match(page, /setRows\(\[\]\)/)
})
test('settings rules are not duplicated in the sidebar or fake alert badges', () => {
  const sidebar=readFileSync(new URL('../components/layout/Sidebar.tsx', import.meta.url),'utf8')
  assert.match(sidebar, /if \(!canOpenRoute\(user\?\.role, 'facility.settings'\) && canOpenRoute\(user\?\.role, 'task_codes'\)\)/)
  assert.doesNotMatch(sidebar, /key: 'nav_shiftcodes'.*path:/)
  assert.doesNotMatch(sidebar, /badge: '3'/)
})
