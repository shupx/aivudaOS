import assert from 'node:assert/strict'
import test from 'node:test'
import { buildAppListGroups, createStartupPipelineApi } from '../aivudaos/resources/ui/src/services/core/startupPipeline.js'

const group = (id, order, items, options) => ({ id, order, items, name: id, ...options })
const item = (app_id, order, options) => ({ app_id, order, ...options })
const app = (app_id, running = false) => ({ app_id, running })
const config = groups => ({ default_profile: 'field', profiles: [
  { name: 'other', groups: [group('ignore', 0, [item('unassigned', 0)])] },
  { name: 'field', groups },
] })

test('list config and two scopes of restart use authenticated pipeline endpoints', async () => {
  const calls = [], api = createStartupPipelineApi(async (...args) => calls.push(args))
  await api.loadForList()
  await api.restart({ profile: 'field', group_id: 'drivers' })
  await api.restart({ profile: 'field' })
  assert.deepEqual(calls, [
    ['/api/apps/pipeline?view=list', { auth: true, method: 'GET', body: undefined }],
    ['/api/apps/pipeline/restart', { auth: true, method: 'POST', body: { profile: 'field', group_id: 'drivers' } }],
    ['/api/apps/pipeline/restart', { auth: true, method: 'POST', body: { profile: 'field' } }],
  ])
})

test('list groups preserve pipeline rank, inventory identity, summaries and disabled groups', () => {
  const apps = [app('unused'), app('c', true), app('b'), app('unassigned', true), app('a', true)]
  const readiness = { type: 'ros2_topic', topic: '/scan', require_publisher: true }
  const profile = config([
    group('last', 9007199254740000, []),
    group('drivers', -8, [item('b', 3), item('a', -2, { readiness, depends_on: ['c'] }), item('gone', 0)], { mode: 'sequential' }),
    group('off', -8, [item('c', 0, { enabled: false })], { enabled: false }),
  ])
  const original = structuredClone(profile), { groups, unassignedApps } = buildAppListGroups(apps, profile)
  assert.deepEqual(groups.map(g => [g.id, g.order, g.enabled, g.mode, g.runningCount]), [
    ['drivers', -8, true, 'sequential', 1], ['off', -8, false, 'parallel', 1],
    ['last', 9007199254740000, true, 'parallel', 0],
  ])
  assert.deepEqual(groups.map(g => g.apps.map(a => a.app_id)), [['a', 'b'], ['c'], []])
  assert.equal(groups[0].apps[0], apps[4])
  assert.deepEqual(groups[0].nodeSummaries.get('a'), { enabled: true, readiness, depends_on: ['c'] })
  assert.deepEqual(groups[1].nodeSummaries.get('c'), { enabled: false, readiness: { type: 'started' }, depends_on: [] })
  assert.deepEqual(unassignedApps, [apps[0], apps[3]])
  assert.deepEqual(profile, original)
  assert.deepEqual(buildAppListGroups(apps, null), { groups: [], unassignedApps: apps })
})

test('rank ties keep their wire order even with negative and sparse out-of-order nodes', () => {
  const ranks = [0, 1e24, -8, 65535, 4, -1e24, -2, -100, -8, 2 ** 32, -0, 4]
  const items = ranks.map((rank, index) => item(`app-${index}`, rank))
  const apps = items.map(({ app_id }) => app(app_id))
  const sorted = [...items].sort((a, b) => a.order - b.order)
  const { groups } = buildAppListGroups(apps, config([group('a', 0, items)]))
  assert.deepEqual(groups[0].apps.map(a => a.app_id), sorted.map(i => i.app_id))
})
