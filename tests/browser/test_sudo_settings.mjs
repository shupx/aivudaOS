// Run after the UI build, with Playwright and its Chromium installed.
import assert from 'node:assert/strict'
import test from 'node:test'
import { dashboardPage } from './fixtures/dashboard.mjs'

test('sudo switch reflects the confirmed server state, including after a rejected password', async t => {
  const writes = []
  let enabled = true
  // Intercept every request: no real gateway, passwords or sudoers file are involved.
  const page = await dashboardPage(t, '/dashboard/settings', async (route, { pathname: path }) => {
    let json = { items: [] }
    if (path.endsWith('/sudo-nopasswd')) {
      if (route.request().method() === 'PUT') {
        const payload = route.request().postDataJSON()
        writes.push(payload.enabled)
        if (payload.sudo_password !== 'accepted-test') return route.fulfill({status: 400, json: {detail: 'Test rejection'}})
        enabled = payload.enabled
      }
      json = { username: 'test-admin', enabled }
    } else if (path.endsWith('/auth/me')) json = { username: 'test-admin', role: 'admin' }
    return route.fulfill({ json })
  })
  const row = page.locator('.setting-row').filter({ hasText: 'Passwordless Sudo' })
  const checkbox = row.getByRole('checkbox')
  await page.getByText('test-admin', {exact: true}).first().waitFor()
  assert.ok(await checkbox.isChecked())
  await row.locator('label.switch').click()
  const password = page.getByPlaceholder('Enter current user sudo password')
  const submit = page.getByRole('button', { name: 'Confirm', exact: true })
  await password.fill('rejected-test')
  await submit.click()
  await page.getByText('Test rejection').waitFor()
  assert.ok(await checkbox.isChecked())
  await password.fill('accepted-test')
  await submit.click()
  await password.waitFor({ state: 'hidden' })
  await page.getByText('System settings saved').waitFor()
  assert.equal(await checkbox.isChecked(), false)
  assert.deepEqual(writes, [false, false])
})
