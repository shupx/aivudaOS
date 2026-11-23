import assert from 'node:assert/strict'
import test from 'node:test'
import { dashboardPage } from './fixtures/dashboard.mjs'
import { analyzeProfile, newGroup, newNode } from '../../aivudaos/resources/ui/src/services/core/startupPipeline.js'

const node = (id, depends_on = []) => ({ ...newNode(id), depends_on })
const group = (id, ...items) => ({ ...newGroup(id, id), items })
const config = (...groups) => ({ version: 4, takeover_autostart: false, default_profile: 'default',
  profiles: [{ name: 'default', on_failure: 'abort', groups }] })
const apps = (...ids) => ids.map(app_id => ({ app_id, name: app_id.toUpperCase(), running: false }))

test('built Apps editor: drag, configure, validate, save and observe a stage run', async t => {
  const installed = apps('a', 'b'), writes = [], runs = [], faults = []
  let cfg = config(group('one', node('a')), group('two'))
  const validation = () => ({ valid: true, errors: [], preview: { default: analyzeProfile(cfg.profiles[0], installed).preview } })
  const page = await dashboardPage(t, '/dashboard/apps', async (route, { pathname }) => {
    const req = route.request()
    let json = { items: [] }
    if (pathname.endsWith('/apps/installed')) json = { items: installed }
    else if (pathname.endsWith('/apps/pipeline')) {
      if (req.method() === 'PUT') { cfg = req.postDataJSON(); writes.push(cfg); cfg = { ...cfg, version: cfg.version + 1 } }
      json = { config: cfg, installed_apps: installed, unassigned_apps: [], active_operation: null, validation: validation() }
    } else if (pathname.endsWith('/pipeline/validate')) json = validation()
    else if (pathname.endsWith('/pipeline/run')) { runs.push(req.postDataJSON()); json = { operation_id: 'op' } }
    else if (pathname.endsWith('/op/events')) {
      return route.fulfill({ contentType: 'text/event-stream', body: [
        ['pipeline_stage', { group_id: 'two', status: 'starting' }],
        ['pipeline_node', { app_id: 'b', group_id: 'two', status: 'waiting_ready' }],
        ['log', { message: 'Probe connected' }], ['completed', { status: 'completed', done: true }],
      ].map(([type, props], index) => `event: ${type}\ndata: ${JSON.stringify({ type, seq: index + 1, ...props })}\n\n`).join('') })
    }
    return route.fulfill({ json })
  })
  page.on('pageerror', err => faults.push(err.message))
  await page.getByText('Startup pipeline', { exact: true }).click()
  const stages = page.locator('.stage'), second = stages.nth(1)
  await page.locator('.pool-node .grip').dragTo(second.locator('.drop-list'))
  await second.locator('.node').waitFor()
  await second.locator('.node-info').click()
  await page.getByText('Process started', { exact: true }).last().click()
  await page.getByText('TCP connection', { exact: true }).last().click()
  const port = page.locator('.n-form-item').filter({ has: page.getByText('Port', { exact: true }) }).locator('input')
  await port.fill('9090'); await port.press('Tab')
  await page.getByRole('button', { name: 'Apply', exact: true }).click()
  await second.getByText('Readiness: TCP connection: 127.0.0.1:9090').waitFor()
  assert.ok(await page.getByRole('button', { name: 'Run profile' }).isDisabled())
  await page.getByText('App list', { exact: true }).click()
  await page.getByText('Startup pipeline', { exact: true }).click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByText('Pipeline saved.').waitFor()
  assert.equal(writes.length, 1); assert.equal(writes[0].version, 4)
  assert.equal(writes[0].profiles[0].groups[1].items[0].readiness.port, 9090)
  await second.getByRole('button', { name: 'Actions for two' }).click()
  await page.getByText('Run stage', { exact: true }).click()
  await second.getByText('Waiting for readiness', { exact: true }).waitFor()
  await page.getByText('Completed', { exact: true }).waitFor()
  await page.getByText('Operation log', { exact: false }).first().click()
  await page.getByText('Probe connected', { exact: true }).waitFor()
  assert.deepEqual(runs, [{ profile: 'default', group_id: 'two' }]); assert.deepEqual(faults, [])
})

test('attached startup operation can be canceled without SSE; conflicting drafts survive until reload is confirmed', async t => {
  const cfg = config(group('one', node('a'))), installed = apps('a'), writes = []
  let canceled = false
  const page = await dashboardPage(t, '/dashboard/apps', async (route, { pathname }) => {
    const req = route.request()
    let json = { items: [] }
    if (pathname.endsWith('/apps/installed')) json = { items: installed }
    else if (pathname.endsWith('/apps/pipeline')) {
      if (req.method() === 'PUT') {
        writes.push(req.postDataJSON()); cfg.version++
        return route.fulfill({ status: 409, json: { detail: 'Pipeline version conflict' } })
      }
      json = { config: cfg, installed_apps: installed, validation: { valid: true, errors: [], preview: {} },
        active_operation: canceled ? null : { operation_id: 'boot', profile: 'default', action: 'run' } }
    } else if (pathname.endsWith('/pipeline/validate')) json = { valid: true, errors: [], preview: {} }
    else if (pathname.endsWith('/boot/events')) return route.abort()
    else if (pathname.endsWith('/boot/cancel') && req.method() === 'POST') canceled = true
    else if (pathname.endsWith('/operations/boot')) json = { status: canceled ? 'canceled' : 'running', done: canceled }
    return route.fulfill({ json })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByText('Startup pipeline', { exact: true }).click()
  await page.getByRole('button', { name: 'Cancel operation' }).click()
  await page.getByText('Canceled', { exact: true }).waitFor()
  assert.ok(canceled)
  const takeover = page.getByRole('switch', { name: 'Use pipeline for autostart' })
  await takeover.click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByText('Pipeline version conflict').waitFor()
  assert.equal(writes[0].takeover_autostart, true); assert.equal(writes[0].version, 4)
  await page.getByRole('button', { name: 'Reload pipeline' }).click()
  await page.getByText('Discard unsaved changes and load the saved pipeline?').waitFor()
  await page.locator('.n-popconfirm__action .n-button').last().click()
  await page.getByText('Pipeline version conflict').waitFor({ state: 'hidden' })
  await page.locator('[role="switch"][aria-label="Use pipeline for autostart"][aria-checked="false"]').waitFor()
  assert.ok(await page.getByRole('button', { name: 'Save changes' }).isDisabled())
  const bounds = await page.locator('.pipeline').evaluate(el => ({ width: el.clientWidth, content: el.scrollWidth }))
  assert.ok(bounds.content <= bounds.width + 1, `pipeline overflows at mobile width: ${JSON.stringify(bounds)}`)
})
