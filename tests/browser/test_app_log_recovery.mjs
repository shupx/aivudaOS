import assert from 'node:assert/strict'
import test from 'node:test'
import { dashboardPage } from './fixtures/dashboard.mjs'

test('clear view follows new logs even if the initial seek fails', async t => {
  const old = 'old output\n'
  const fresh = 'new error during outage\n'
  let file = old
  let failSeek = true
  let retryOffset
  const page = await dashboardPage(t, '/dashboard/apps/demo', async (route, { pathname: path, searchParams }) => {
    let json = { items: [] }
    if (path.endsWith('/auth/me')) json = { username: 'test', role: 'admin' }
    if (path.endsWith('/apps/installed')) json = { items: [{ app_id: 'demo', active_version: '1', versions: ['1'] }] }
    if (path.endsWith('/demo/logs')) {
      const offset = Number(searchParams.get('offset'))
      if (searchParams.get('from_end') === 'true') {
        if (!failSeek) return route.fulfill({ json: { size: file.length, next_offset: file.length, chunk: '', reset: false } })
        failSeek = false
        file += fresh
        return route.fulfill({ status: 503, json: { detail: 'temporary outage' } })
      }
      if (!failSeek && retryOffset === undefined) retryOffset = offset
      json = { size: file.length, next_offset: file.length, chunk: file.slice(offset), reset: false }
    }
    return route.fulfill({ json })
  }, 8000)
  const output = page.locator('.app-log-output')
  await output.filter({ hasText: old.trim() }).waitFor()
  await page.getByRole('button', { name: 'Clear view' }).click()
  await output.filter({ hasText: fresh.trim() }).waitFor()
  assert.equal(retryOffset, old.length)
  assert.equal(await output.textContent(), fresh)
  // A later successful clear still skips already-written, unread history.
  file += 'before clear\n'
  const sought = page.waitForResponse(response => new URL(response.url()).searchParams.get('from_end') === 'true')
  await page.getByRole('button', { name: 'Clear view' }).click()
  await sought
  file += 'after clear\n'
  await output.filter({ hasText: 'after clear' }).waitFor()
  assert.equal(await output.textContent(), 'after clear\n')
})
