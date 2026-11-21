// Run after building the UI. All gateway responses are local fixtures.
import assert from 'node:assert/strict'
import test from 'node:test'
import { dashboardPage } from './fixtures/dashboard.mjs'

async function configPage(t) {
  const sys = { version: 1, data: { sys: { ros2_default_domain_id: 17 } }, ros2_detected: true }
  const app = {
    app_id: 'demo', name: 'Demo', version: 1, app_version: '1.0.0',
    data: { ros_domain_id: null, dds_domain: '8' }, default_data: { ros_domain_id: '7' },
    schema: { properties: {
      ros_domain_id: { type: ['string', 'null'], enum: ['7', '08', null] },
      dds_domain: { type: ['null', 'string'] },
    } },
  }
  const writes = []
  const page = await dashboardPage(t, '/dashboard/apps/configs', async (route, { pathname: path }) => {
    let json = { items: [] }
    if (route.request().method() === 'PUT') {
      const data = route.request().postDataJSON().data
      const resource = path.endsWith('/apps/demo/config') ? app : sys
      resource.data = data
      writes.push(data)
      json = { version: ++resource.version, runtime_environment_refresh_errors: resource === sys ? ['demo.service: permission denied'] : [] }
    } else if (path.endsWith('/apps/configs/active')) json = { items: [app] }
    else if (path.endsWith('/api/config')) json = sys
    else if (path.endsWith('/auth/me')) json = { username: 'test-admin', role: 'admin' }
    return route.fulfill({ json })
  })
  await page.getByRole('heading', { name: 'ROS 2 Domain Parameters' }).waitFor()
  return { page, writes }
}

test('the ROS domain section is hidden in a specific app config and returns in the overview', async t => {
  const { page } = await configPage(t)
  await page.goto('http://ui.test/dashboard/apps/configs?app_id=demo')
  const appFilter = page.locator('#config-center-app-select-inline')
  await appFilter.locator('option[value="demo"]:checked').waitFor({ state: 'attached' })
  const section = page.getByRole('heading', { name: 'ROS 2 Domain Parameters' })
  assert.equal(await section.count(), 0)
  await appFilter.selectOption('')
  await section.waitFor()
})

test('Domain editors save typed string and null values, including enumerated launch defaults', async t => {
  const { page, writes } = await configPage(t)
  const enumField = page.getByRole('combobox', { name: 'Demo ros_domain_id' })
  const enumRow = page.getByRole('row').filter({ has: enumField })
  assert.equal(await enumField.locator('option:checked').innerText(), 'Launch default')
  await enumField.selectOption({ label: '08' })
  await enumRow.getByRole('button', { name: 'Save' }).click()
  await enumRow.getByText('Launch default (17)').waitFor({ state: 'hidden' })
  assert.equal(writes[0].ros_domain_id, '08')
  await enumField.selectOption({ label: 'Launch default' })
  await enumRow.getByRole('button', { name: 'Save' }).click()
  await enumRow.getByText('Launch default (17)').waitFor()
  assert.equal(writes[1].ros_domain_id, null)

  const freeField = page.getByRole('textbox', { name: 'Demo dds_domain' })
  await freeField.fill('001')
  const saved = page.waitForResponse(response => response.request().method() === 'PUT' && response.url().includes('/demo/config'))
  await freeField.press('Enter')
  await saved
  const row = page.getByRole('row').filter({ has: freeField })
  await page.getByRole('textbox', { name: 'Demo dds_domain', disabled: false }).waitFor()
  assert.equal(writes[2].dds_domain, '001')
  await freeField.fill('')
  await freeField.press('Enter')
  await row.getByText('Launch default (17)').waitFor()
  assert.equal(writes[3].dds_domain, null)
})

test('manual import reports failed unit refresh, continues app writes, and resets warning for an app-only import', async t => {
  const { page, writes } = await configPage(t)
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  async function apply(payload) {
    await page.locator('input[type=file][accept*="json"]').setInputFiles({
      name: 'import.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ format_version: 1, payload })),
    })
    await page.getByRole('button', { name: 'Apply Selected' }).click()
  }
  const apps = [{ app_id: 'demo', version: '1.0.0', parameters: { dds_domain: '9' } }]
  await apply({ system_parameters: { sys: { ros2_default_domain_id: 22 } }, apps })
  const warning = page.getByText('Settings saved, but some systemd units could not be refreshed: demo.service: permission denied')
  await warning.waitFor()
  await page.getByRole('button', { name: 'Apply Selected', disabled: true }).waitFor()
  assert.deepEqual(writes, [{ sys: { ros2_default_domain_id: 22 } }, { ros_domain_id: null, dds_domain: '9' }])
  assert.equal(await page.getByText('Selected parameters imported').count(), 0)
  apps[0].parameters.dds_domain = '10'
  await apply({ apps })
  await page.getByText('Selected parameters imported').waitFor()
  assert.equal(await warning.count(), 0)
  assert.deepEqual(writes.slice(2), [{ ros_domain_id: null, dds_domain: '10' }])
})
