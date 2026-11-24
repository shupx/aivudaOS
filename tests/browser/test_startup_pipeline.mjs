import assert from 'node:assert/strict'
import test from 'node:test'
import { dashboardPage } from './fixtures/dashboard.mjs'

const app = app_id => ({ app_id, name: app_id.toUpperCase(), running: false })
const node = app_id => ({ app_id, order: 0, enabled: true, depends_on: [], readiness: { type: 'started' } })
const group = (id, order, ...items) => ({ id, name: id, order, mode: 'parallel', enabled: true, items })
const initial = () => ({ version: 4, takeover_autostart: false, default_profile: 'default', profiles: [{
  name: 'default', on_failure: 'abort', groups: [group('first', 0, node('alpha')), group('second', 1, node('beta'))],
}] })
const installed = ['alpha', 'beta', 'gamma'].map(app)
const valid = { valid: true, errors: [], preview: {} }
const events = entries => entries.map(([type, payload], i) => `event: ${type}\ndata: ${JSON.stringify({ type, seq: i + 1, ...payload })}\n\n`).join('')

// Browser-only gateway stub. Observe real request bodies; the test never mutates
// application state or calls Vue Flow's internal move/connect methods.
async function appsPage(t, { active = false, conflict = false, stream, cfg = initial() } = {}) {
  const state = { cfg, installed: [...installed], writes: [], runs: [], actions: [], configViews: [], faults: [], canceled: false }
  const page = await dashboardPage(t, '/dashboard/apps', async (route, { pathname, searchParams }) => {
    const req = route.request()
    let json = { items: [] }
    if (pathname.endsWith('/apps/installed')) json = { items: state.installed }
    else if (pathname.endsWith('/apps/pipeline')) {
      if (req.method() === 'PUT') {
        const draft = req.postDataJSON(); state.writes.push(draft)
        if (conflict) { state.cfg.version++; return route.fulfill({ status: 409, json: { detail: 'Pipeline version conflict' } }) }
        assert.equal(draft.version, state.cfg.version)
        state.cfg = { ...draft, version: state.cfg.version + 1 }
      }
      const list = searchParams.get('view') === 'list'
      if (req.method() === 'GET') state.configViews.push(list ? 'list' : 'editor')
      json = { config: state.cfg, active_operation: active && !state.canceled ? {
        operation_id: 'boot', profile: 'default', action: 'run', ...(typeof active === 'object' ? active : {}),
      } : null }
      if (!list) Object.assign(json, { installed_apps: state.installed, unassigned_apps: [], validation: valid })
    } else if (pathname.endsWith('/pipeline/validate')) json = valid
    else if (/\/pipeline\/(run|restart|stop)$/.test(pathname)) {
      const action = pathname.split('/').pop(), scope = req.postDataJSON()
      state.actions.push({ action, scope })
      if (action === 'run') state.runs.push(scope)
      json = { operation_id: `${action}-${state.actions.length}` }
    }
    else if (/\/operations\/[^/]+\/events$/.test(pathname)) {
      if (stream) return route.fulfill({ contentType: 'text/event-stream', body: await stream() })
      return route.abort()
    } else if (pathname.endsWith('/boot/cancel') && req.method() === 'POST') state.canceled = true
    else if (pathname.endsWith('/operations/boot')) json = { status: state.canceled ? 'canceled' : 'running', done: state.canceled }
    return route.fulfill({ json })
  })
  page.on('pageerror', err => state.faults.push(err.message))
  return { page, state }
}

async function editor(t, options) {
  const { page, state } = await appsPage(t, options)
  // The list loads the default profile as JSON and leaves the graph runtime and CSS behind the tab.
  await page.locator('.app-list-stage').first().waitFor()
  assert.equal(await page.evaluate(() => performance.getEntriesByType('resource').some(e => /StartupPipelinePanel|vue-flow/i.test(e.name))), false)
  await page.getByText('Startup pipeline', { exact: true }).click()
  await page.locator('.vue-flow__node').first().waitFor()
  return { page, state }
}

test('App list loads only the lightweight config and sends group and global actions to the pipeline', async t => {
  const { page, state } = await appsPage(t, { stream: () => events([['completed', { done: true, status: 'completed' }]]) })
  const first = page.getByRole('region', { name: 'first', exact: true })
  await first.locator('#app-card-alpha').waitFor()
  await page.getByRole('region', { name: 'Unassigned apps' }).locator('#app-card-gamma').waitFor()
  assert.deepEqual(state.configViews, ['list'])
  assert.equal(await page.locator('.stage-connector').count(), 1)
  const search = page.getByPlaceholder('Search by app name and jump')
  await search.fill('gamma')
  await search.press('Enter')
  await page.waitForFunction(() => document.getElementById('app-card-gamma')?.style.borderWidth === '2px')

  for (const [label, action] of [['Start', 'run'], ['Restart', 'restart'], ['Stop', 'stop']]) {
    await Promise.all([
      page.waitForRequest(r => r.method() === 'POST' && r.url().includes(`/pipeline/${action}?`)),
      first.getByRole('button', { name: `${label} group first`, exact: true }).click(),
    ])
  }
  await page.getByRole('button', { name: 'Group by pipeline', exact: true }).click()
  await first.waitFor({ state: 'detached' })
  assert.equal(await page.locator('.apps-grid .apps-app-card').count(), 3)
  for (const [label, action] of [['Start default pipeline', 'run'], ['Restart default pipeline', 'restart'], ['Stop default pipeline in reverse order', 'stop']]) {
    await Promise.all([
      page.waitForRequest(r => r.method() === 'POST' && r.url().includes(`/pipeline/${action}?`)),
      page.getByRole('button', { name: label, exact: true }).click(),
    ])
  }
  assert.deepEqual(state.actions, [{ profile: 'default', group_id: 'first' }, {}].flatMap(scope =>
    ['run', 'restart', 'stop'].map(action => ({ action, scope }))))
  const resources = await page.evaluate(() => performance.getEntriesByType('resource').map(e => e.name))
  assert.ok(resources.every(name => !/StartupPipelinePanel|vue-flow|pipelineGraph/i.test(name)))
  assert.deepEqual(state.faults, [])
})

test('the list can cancel an attached group restart and restores its controls on completion', async t => {
  const { page, state } = await appsPage(t, { active: { group_id: 'first', action: 'restart' } })
  const group = page.getByRole('region', { name: 'first', exact: true })
  await group.getByRole('button', { name: 'Cancel', exact: true }).click()
  await group.getByRole('button', { name: 'Restart group first', exact: true }).waitFor()
  assert.ok(state.canceled)
  assert.deepEqual(state.faults, [])
})

test('empty default profile keeps the flat list and legacy bulk controls', async t => {
  const cfg = initial(); cfg.profiles[0].groups = []
  const { page } = await appsPage(t, { cfg })
  await page.getByTitle('Restart all currently running apps').waitFor()
  assert.equal(await page.locator('.app-list-stage').count(), 0)
  assert.equal(await page.getByTitle('Start default pipeline').count(), 0)
  await page.locator('#app-card-gamma').waitFor()
})

test('leaving the editor flushes the draft and returning updates the app pool', async t => {
  const { page, state } = await editor(t)
  await page.getByRole('button', { name: 'Add group', exact: true }).click()
  await page.getByText('App list', { exact: true }).click()
  await page.locator('.app-list-stage[data-group-id="stage-3"]').waitFor()
  assert.equal(state.writes.length, 1)
  state.installed = [app('alpha'), app('beta'), app('delta')]
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await page.locator('#app-card-delta').waitFor()
  await page.getByText('Startup pipeline', { exact: true }).click()
  await page.locator('.tray-toggle').click()
  await page.locator('.pool-app[data-app-id="delta"]').waitFor()
  assert.equal(await page.locator('.pool-app[data-app-id="gamma"]').count(), 0)
  await page.getByRole('button', { name: 'Add group', exact: true, disabled: false }).waitFor()
  const fullReads = state.configViews.filter(view => view === 'editor').length
  await page.getByText('App list', { exact: true }).click()
  await page.getByRole('button', { name: 'Start group first', exact: true, disabled: false }).waitFor()
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/apps/pipeline?view=list')),
    page.getByText('Startup pipeline', { exact: true }).click(),
  ])
  await page.getByRole('button', { name: 'Add group', exact: true }).waitFor()
  assert.equal(state.configViews.filter(view => view === 'editor').length, fullReads)
  assert.deepEqual(state.faults, [])
})

async function drag(page, start, end, whileHeld) {
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  try {
    await page.mouse.move(end.x, end.y, { steps: 18 })
    await whileHeld?.()
  } finally { await page.mouse.up() }
}
async function center(locator) {
  const rect = await locator.boundingBox()
  assert.ok(rect, 'drag target is visible')
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
}
async function editAndSave(page, action) {
  const [response] = await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/apps/pipeline?') && r.request().method() === 'PUT'),
    action(),
  ])
  assert.equal(response.status(), 200)
  return response.request().postDataJSON()
}
const canvasApp = (page, id) => page.locator(`.pipeline-app[data-app-id="${id}"]`)
const canvasGroup = (page, id) => page.locator(`.pipeline-group[data-group-id="${id}"]`)
const item = (cfg, id) => cfg.profiles[0].groups.flatMap(g => g.items).find(n => n.app_id === id)

test('handle gestures add and remove dependencies; dragging across stage boundaries reparents and autosaves', async t => {
  const { page, state } = await editor(t)
  const alpha = canvasApp(page, 'alpha'), beta = canvasApp(page, 'beta')
  assert.equal(await page.getByRole('button', { name: 'Save changes' }).count(), 0)
  const connected = await editAndSave(page, async () => {
    await drag(page, await center(alpha.locator('.vue-flow__handle.source')), await center(beta.locator('.vue-flow__handle.target')))
  })
  assert.deepEqual(item(connected, 'beta').depends_on, ['alpha'])

  const disconnected = await editAndSave(page, async () => {
    const path = page.locator('.vue-flow__edge[data-id^="dependency:"] .vue-flow__edge-path')
    const point = await path.evaluate(el => {
      // The stage-order edge can cross the dependency curve. Hit a visible
      // segment of the dependency, not a different edge or an app on top of it.
      for (let fraction = 0.05; fraction < 1; fraction += 0.05) {
        const p = el.getPointAtLength(el.getTotalLength() * fraction).matrixTransform(el.getScreenCTM())
        if (document.elementFromPoint(p.x, p.y)?.closest('.vue-flow__edge') === el.closest('.vue-flow__edge')) return { x: p.x, y: p.y }
      }
    })
    assert.ok(point, 'dependency edge has a clickable segment')
    await page.mouse.click(point.x, point.y)
    assert.ok(await path.evaluate(el => el.closest('.vue-flow__edge').classList.contains('selected')))
    await page.keyboard.press('Delete')
  })
  assert.deepEqual(item(disconnected, 'beta').depends_on, [])
  const moved = await editAndSave(page, async () => {
    const groupBounds = await canvasGroup(page, 'first').boundingBox()
    await drag(page, await center(beta), { x: groupBounds.x + groupBounds.width * 0.6, y: groupBounds.y + groupBounds.height * 0.7 }, async () => {
      // Hold past the debounce window: pointer-move alone must never schedule a save.
      await page.waitForTimeout(650)
      assert.equal(state.writes.length, 2)
    })
  })
  assert.deepEqual(moved.profiles[0].groups[0].items.map(n => n.app_id).sort(), ['alpha', 'beta'])
  assert.equal(moved.profiles[0].groups[1].items.length, 0)
  assert.ok(Object.keys(moved.profiles[0].layout).length)
  assert.equal(state.writes.length, 3, 'one debounced save per completed gesture')
  assert.deepEqual(state.faults, [])
})

test('dropping outside all groups grows the original group and auto arrange discards saved dimensions', async t => {
  const { page, state } = await editor(t)
  const source = canvasApp(page, 'alpha'), stage = canvasGroup(page, 'first')
  const from = await center(source), bounds = await stage.boundingBox()
  const destination = { x: from.x, y: bounds.y + bounds.height + 24 }
  const moved = await editAndSave(page, () => drag(page, from, destination))
  assert.equal(await source.getAttribute('data-group-id'), 'first')
  assert.ok((await stage.boundingBox()).height > bounds.height)
  assert.deepEqual(moved.profiles[0].groups[0].items.map(item => item.app_id), ['alpha'])
  const arranged = await editAndSave(page, () => page.getByRole('button', { name: 'Auto arrange' }).click())
  assert.ok(Object.values(arranged.profiles[0].layout).every(box => !('w' in box) && !('h' in box)))
  assert.deepEqual(state.faults, [])
})

test('collapsed tray assigns an installed app to the canvas and persists its configuration', async t => {
  const { page, state } = await editor(t)
  const tray = page.locator('.tray-toggle'), poolApp = page.locator('.pool-app[data-app-id="gamma"]')
  assert.equal(await tray.getAttribute('aria-expanded'), 'false'); assert.equal(await poolApp.isVisible(), false)
  await tray.click()
  const cfg = await editAndSave(page, () => poolApp.dragTo(canvasGroup(page, 'second'), { targetPosition: { x: 50, y: 45 } }))
  assert.ok(cfg.profiles[0].groups.find(g => g.id === 'second').items.some(n => n.app_id === 'gamma'))
  await canvasApp(page, 'gamma').waitFor(); await poolApp.waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: 'Configure GAMMA', exact: true }).click()
  const form = page.locator('#pipeline-node-form')
  await form.getByLabel('Readiness check').selectOption('delay')
  await form.getByLabel('Delay (seconds)', { exact: true }).fill('3')
  const saved = await editAndSave(page, () => page.getByRole('button', { name: 'Apply', exact: true }).click())
  assert.deepEqual(item(saved, 'gamma').readiness, { type: 'delay', delay_sec: 3, timeout_sec: 30, interval_sec: 1 })
  await canvasApp(page, 'gamma').getByText('3 s', { exact: true }).waitFor()
  assert.deepEqual(state.faults, [])
})

test('a group run consumes named SSE without remounting graph nodes', async t => {
  const cfg = initial(); item(cfg, 'beta').depends_on = ['alpha']
  const frames = [
    ['pipeline_stage', { group_id: 'second', status: 'starting' }],
    ['pipeline_node', { group_id: 'first', app_id: 'alpha', status: 'active' }],
    ['pipeline_node', { group_id: 'second', app_id: 'beta', status: 'waiting_ready' }],
    ['log', { message: 'Waiting for probe' }],
  ]
  let opened = false, finish
  const terminal = new Promise(resolve => { finish = resolve })
  t.after(finish)
  // A replay after reconnect lets the browser paint intermediate status before
  // completing the run without replacing the native EventSource with a stub.
  const { page, state } = await editor(t, { cfg, stream: async () => {
    if (!opened) { opened = true; return 'retry: 100\n\n' + events(frames) }
    await terminal
    return events([...frames, ['completed', { status: 'completed', done: true }]])
  } })
  const beta = canvasApp(page, 'beta'), alpha = canvasApp(page, 'alpha')
  const oldBeta = await beta.elementHandle(), oldAlpha = await alpha.elementHandle()
  await page.getByRole('button', { name: 'Run second', exact: true }).click()
  await beta.locator('[data-status="waiting_ready"]').waitFor()
  const animated = page.locator('.vue-flow__edge[data-id^="dependency:"].animated')
  await animated.waitFor({ state: 'attached' }) // A horizontal SVG path can have zero bounding-box height.
  finish()
  await page.getByText('Completed', { exact: true }).waitFor()
  await alpha.locator('[data-status="idle"]').waitFor() // The live inventory has alpha stopped.
  await animated.waitFor({ state: 'detached' })
  assert.deepEqual(state.runs, [{ profile: 'default', group_id: 'second' }])
  assert.ok(await beta.evaluate((node, old) => node === old, oldBeta)); assert.ok(await alpha.evaluate((node, old) => node === old, oldAlpha))
  assert.equal(state.writes.length, 0, 'runtime telemetry must not trigger an autosave')
  assert.deepEqual(state.faults, [])
})

test('cancel an attached run over the polling fallback and recover from a settings autosave conflict', async t => {
  const { page, state } = await editor(t, { active: true, conflict: true })
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByText('Canceled', { exact: true }).waitFor()
  assert.ok(state.canceled)
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  const takeover = page.getByRole('switch', { name: 'Use pipeline for autostart' })
  await takeover.check()
  await page.getByText('Pipeline version conflict', { exact: true }).waitFor()
  assert.equal(state.writes.length, 1); assert.equal(state.writes[0].takeover_autostart, true)
  assert.equal(state.writes[0].version, 4); assert.ok(await takeover.isChecked())
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Reload pipeline' }).click()
  await page.getByText('Discard unsaved changes and load the saved pipeline?').waitFor()
  await page.locator('.n-popconfirm__action .n-button').last().click()
  await page.getByText('Pipeline version conflict', { exact: true }).waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await takeover.waitFor(); assert.equal(await takeover.isChecked(), false)
  assert.deepEqual(state.faults, [])
})
