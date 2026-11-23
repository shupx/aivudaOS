import assert from 'node:assert/strict'
import test from 'node:test'
import {
  analyzeProfile, applyOperationEvent, applyRos2Template, createStartupPipelineApi, editableConfig,
  newGroup, newNode, newProgress, newReadiness, normalizeOrder, readinessFields, ros2Stages, unassignedNodes,
} from '../aivudaos/resources/ui/src/services/core/startupPipeline.js'
import en from '../aivudaos/resources/ui/src/i18n/locales/en-US.js'
import zh from '../aivudaos/resources/ui/src/i18n/locales/zh-CN.js'

const node = (id, depends_on = []) => ({ ...newNode(id), depends_on })
const group = (id, ...items) => ({ ...newGroup(id, id), items })
const config = (...groups) => ({ version: 4, takeover_autostart: false, default_profile: 'default',
  profiles: [{ name: 'default', on_failure: 'abort', groups }] })
const apps = (...ids) => ids.map(app_id => ({ app_id, name: app_id.toUpperCase(), running: false }))

test('use raw config, profile and group request bodies on authenticated endpoints', async () => {
  const calls = [], api = createStartupPipelineApi(async (...args) => calls.push(args)), cfg = config()
  await api.load(); await api.validate(cfg); await api.save(cfg)
  await api.run({ profile: 'field', group_id: 'hardware' }); await api.stop({ profile: 'lab' })
  assert.deepEqual(calls, [
    ['', 'GET', undefined], ['/validate', 'POST', cfg], ['', 'PUT', cfg],
    ['/run', 'POST', { profile: 'field', group_id: 'hardware' }], ['/stop', 'POST', { profile: 'lab' }],
  ].map(([suffix, method, body]) => ['/api/apps/pipeline' + suffix, { auth: true, method, body }]))
})

test('draft sort is stable; drag between groups normalizes order without dropping readiness or dependencies', () => {
  const last = group('last', node('a'), node('b', ['a'])), first = group('first')
  last.order = 10; last.items[1].readiness = { type: 'ros2_topic', topic: '/scan' }
  const original = config(last, first), draft = editableConfig(original), groups = draft.profiles[0].groups
  assert.deepEqual(groups.map(g => g.id), ['first', 'last'])
  groups[0].items.push(groups[1].items.shift()); normalizeOrder(groups)
  assert.deepEqual(groups.map(g => [g.order, g.items.map(n => n.order)]), [[0, [0]], [1, [0]]])
  assert.deepEqual(groups[1].items[0].depends_on, ['a'])
  assert.deepEqual(groups[1].items[0].readiness, { type: 'ros2_topic', topic: '/scan' })
  assert.equal(original.profiles[0].groups[0].items.length, 2)
  assert.deepEqual(unassignedNodes(draft.profiles[0], apps('a', 'b', 'c')), [newNode('c')])
  assert.equal(draft.version, 4)
})

test('ROS 2 template is repeatable and keeps custom stages, stage names and assignments', () => {
  const p = { groups: [group('other', node('alpha')), { ...group('perception', node('beta')), name: 'Custom vision' }] }
  applyRos2Template(p); applyRos2Template(p)
  assert.deepEqual(p.groups.map(g => g.id), ['middleware', 'hardware', 'perception', 'planning', 'telemetry', 'other'])
  assert.equal(p.groups[2].name, 'Custom vision'); assert.equal(p.groups[2].items[0].app_id, 'beta')
  assert.equal(p.groups[5].items[0].app_id, 'alpha')
  assert.deepEqual(p.groups.map(g => g.order), [0, 1, 2, 3, 4, 5])
})

test('preview respects stage barriers and selects newly ready lower-ranked nodes in sequential mode', () => {
  const groups = [group('start', node('s')), group('work', node('a', ['b']), node('b', ['s']), node('c')),
    { ...group('off', node('z')), enabled: false }]
  groups[1].items.push({ ...node('d', ['c']), enabled: false })
  const analyze = () => analyzeProfile({ groups }, apps('s', 'a', 'b', 'c', 'd', 'z'))
  assert.deepEqual(analyze(), { errors: [], preview: [
    { group_id: 'start', batches: [['s']] }, { group_id: 'work', batches: [['b', 'c'], ['a']] },
  ] })
  groups[1].mode = 'sequential'
  assert.deepEqual(analyze().preview[1].batches, [['b'], ['a'], ['c']])
})

test('conflicts identify cycle members, reverse-stage edges, unassigned and disabled prerequisites', () => {
  const analysis = (...groups) => analyzeProfile({ groups }, apps('a', 'b', 'c'))
  assert.deepEqual(analysis(group('one', node('a', ['b']), node('b', ['a']))).errors[0].apps, ['a', 'b'])
  assert.equal(analysis(group('one', node('a', ['a']))).errors[0].code, 'cycle')
  assert.equal(analysis(group('one', node('a', ['b'])), group('two', node('b'))).errors[0].code, 'reverse')
  assert.equal(analysis(group('one', node('a', ['b']))).errors[0].code, 'missing')
  assert.equal(analysis(group('one', { ...node('b'), enabled: false }, node('a', ['b']))).errors[0].code, 'disabled')
  assert.equal(analysis({ ...group('off', node('b')), enabled: false }, group('on', node('a', ['b']))).errors[0].code, 'disabled')
  assert.equal(analysis(group('one', node('a'), node('a'))).errors[0].code, 'duplicate')
  assert.equal(analysis(group('one', node('gone'))).errors[0].code, 'notInstalled')
  assert.deepEqual(analysis(group('one', node('gone'))).preview, [])
})

test('node/stage/log events are independent, bounded, scoped to the operation and replay-safe', () => {
  const state = newProgress({ operation_id: 'op', profile: 'default' })
  for (const event of [
    { type: 'status', status: 'running' }, { type: 'pipeline_stage', group_id: 'g', status: 'starting' },
    { type: 'pipeline_node', app_id: 'x', group_id: 'g', status: 'waiting_ready' },
    { type: 'log', message: 'checking', seq: 4 }, { type: 'log', message: 'checking', seq: 4 },
    { type: 'completed', operation_id: 'old', status: 'completed' },
  ]) applyOperationEvent(state, event)
  assert.equal(state.stages.get('g'), 'starting'); assert.equal(state.nodes.get('x'), 'waiting_ready')
  assert.equal(state.status, 'running'); assert.deepEqual(state.logs, ['checking'])
  for (let i = 0; i < 320; i++) applyOperationEvent(state, { type: 'log', message: i.toString() })
  assert.equal(state.logs.length, 300)
  applyOperationEvent(state, { type: 'error', done: true, status: 'failed', message: 'probe timeout' })
  applyOperationEvent(state, { type: 'completed', status: 'completed' })
  assert.equal(state.done, true); assert.equal(state.status, 'failed'); assert.equal(state.logs.at(-1), 'probe timeout')
})

test('all readiness fields, states and stage names are available in both languages', () => {
  const leaves = (obj, prefix = '') => Object.entries(obj).flatMap(([key, value]) => {
    assert.ok(value); return typeof value === 'string' ? [prefix + key] : leaves(value, prefix + key + '.')
  }).sort()
  assert.deepEqual(leaves(en.pipeline), leaves(zh.pipeline))
  for (const lang of [en.pipeline, zh.pipeline]) {
    for (const [type, fields] of Object.entries(readinessFields)) {
      assert.ok(lang.probes[type]); const probe = newReadiness(type)
      for (const field of fields) { assert.ok(lang.fields[field]); assert.ok(Object.hasOwn(probe, field)) }
    }
    for (const [stage] of ros2Stages) assert.ok(lang.stages[stage])
    for (const key of ['idle','queued','starting','waiting_ready','active','degraded','failed','skipped','stopping','stopped']) assert.ok(lang.states[key])
  }
  assert.equal(newReadiness('tcp').host, '127.0.0.1'); assert.equal(newReadiness('ros2_topic').require_publisher, false)
  assert.equal(newReadiness('delay').delay_sec, 1); assert.equal(newReadiness('ros2_lifecycle').lifecycle_state, 'active')
})
