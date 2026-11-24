import assert from 'node:assert/strict'
import test from 'node:test'
import './startup_pipeline_list_cases.mjs'
import {
  applyOperationEvent, applyRos2Template, createStartupPipelineApi, editableConfig, pipelineSaveError, profileIssues,
  newGroup, newNode, newProgress, newReadiness, normalizeOrder, readinessFields, ros2Stages, unassignedNodes,
} from '../aivudaos/resources/ui/src/services/core/startupPipeline.js'
import {
  applyAutoLayout, applyConnect, applyDisconnect, applyGroupOrder, applyMoveToGroup, GRAPH_SIZE,
  isEdgeAnimated, pipelineNodeStatus, toFlowGraph,
} from '../aivudaos/resources/ui/src/services/core/pipelineGraph.js'
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

test('autosave serializes overlapping edits and acknowledges only the revision that was sent', async () => {
  const { usePipelineAutosave } = await import('../aivudaos/resources/ui/src/composables/usePipelineAutosave.js')
  const draft = { value: { version: 4, name: 'first' } }, writes = [], completions = [], accepted = []
  const api = { save(value) {
    writes.push({ ...value })
    return new Promise(resolve => completions.push(resolve))
  } }
  const saver = usePipelineAutosave(draft, api, { value: '' }, data => accepted.push(data.config.version))
  try {
    saver.mark()
    const settled = saver.flush()
    draft.value.name = 'newer'
    saver.mark()
    assert.deepEqual(writes, [{ version: 4, name: 'first' }])
    completions[0]({ config: { version: 5, name: 'first' } })
    await new Promise(resolve => setImmediate(resolve))
    assert.deepEqual(writes[1], { version: 5, name: 'newer' })
    assert.deepEqual(accepted, [])
    completions[1]({ config: { version: 6, name: 'newer' } })
    assert.equal(await settled, true)
    assert.deepEqual(accepted, [6]); assert.equal(saver.dirty.value, false)
  } finally { saver.dispose() }
})

test('autosave keeps a conflict draft and pauses writes until a drag finishes', async () => {
  const { usePipelineAutosave } = await import('../aivudaos/resources/ui/src/composables/usePipelineAutosave.js')
  const draft = { value: { version: 4 } }, error = { value: '' }; let count = 0
  const api = { async save() { count++; throw Object.assign(new Error('Version conflict'), { status: 409 }) } }
  const saver = usePipelineAutosave(draft, api, error, () => {})
  try {
    saver.mark(); saver.pause()
    assert.equal(await saver.flush(), false); assert.equal(count, 0)
    saver.resume(); assert.equal(await saver.flush(), false)
    assert.equal(saver.saveState.value, 'conflict'); assert.equal(error.value, 'Version conflict')
    saver.mark(); await saver.retry(); await saver.flush()
    assert.equal(count, 1); assert.equal(saver.dirty.value, true); assert.equal(draft.value.version, 4)
  } finally { saver.dispose() }
})

test('ROS 2 template is repeatable and keeps custom stages, stage names and assignments', () => {
  const p = { groups: [group('other', node('alpha')), { ...group('perception', node('beta')), name: 'Custom vision', depends_on: ['other'] }] }
  applyRos2Template(p); applyRos2Template(p)
  assert.deepEqual(p.groups.map(g => g.id), ['middleware', 'hardware', 'perception', 'planning', 'telemetry', 'other'])
  assert.equal(p.groups[2].name, 'Custom vision'); assert.equal(p.groups[2].items[0].app_id, 'beta')
  assert.equal(p.groups[5].items[0].app_id, 'alpha')
  assert.deepEqual(p.groups.map(g => g.depends_on), [[], ['middleware'], ['other'], ['perception'], ['planning'], []])
  assert.deepEqual(p.groups.map(g => g.order), [0, 1, 2, 3, 4, 5])
})

test('template fills missing stages without closing existing cycles or reconnecting user cuts', () => {
  const p = { groups: [] }
  applyRos2Template(p)
  assert.deepEqual(p.groups.map(g => g.depends_on), [[], ['middleware'], ['hardware'], ['perception'], ['planning']])
  p.groups[0].depends_on = ['hardware']
  p.groups[2].depends_on = []
  p.groups.splice(1, 1)
  applyRos2Template(p)
  assert.deepEqual(p.groups.slice(0, 3).map(g => g.depends_on), [['hardware'], [], []])
})

// Independent, deliberately simple reference for checking the ranked graph scheduler.
function analyzeProfile(profile, installed) {
  const errors = profileIssues(profile, installed), preview = []
  if (!errors.length) for (const group of profile.groups.filter(g => g.enabled !== false)) {
    const nodes = new Map(group.items.map(node => [node.app_id, node]))
    const pending = new Set(group.items.filter(n => n.enabled !== false).map(n => n.app_id))
    const batches = []
    while (pending.size) {
      const ready = [...pending].filter(id => !nodes.get(id).depends_on.some(dep => pending.has(dep)))
      const batch = group.mode === 'sequential' ? ready.slice(0, 1) : ready
      assert.ok(batch.length, 'a validated DAG has a ready frontier')
      batches.push(batch)
      batch.forEach(id => pending.delete(id))
    }
    preview.push({ group_id: group.id, batches })
  }
  return { errors, preview }
}

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

test('conflicts identify cycle members, unrestricted group positions, unassigned and disabled prerequisites', () => {
  const analysis = (...groups) => analyzeProfile({ groups }, apps('a', 'b', 'c'))
  assert.deepEqual(analysis(group('one', node('a', ['b']), node('b', ['a']))).errors[0].apps, ['a', 'b'])
  assert.equal(analysis(group('one', node('a', ['a']))).errors[0].code, 'cycle')
  assert.deepEqual(analysis(group('one', node('a', ['b'])), group('two', node('b'))).errors, [])
  assert.equal(analysis(group('one', node('a', ['b']))).errors[0].code, 'missing')
  assert.equal(analysis(group('one', { ...node('b'), enabled: false }, node('a', ['b']))).errors[0].code, 'disabled')
  assert.equal(analysis({ ...group('off', node('b')), enabled: false }, group('on', node('a', ['b']))).errors[0].code, 'disabled')
  assert.equal(analysis(group('one', node('a'), node('a'))).errors[0].code, 'duplicate')
  assert.equal(analysis(group('one', node('gone'))).errors[0].code, 'notInstalled')
  assert.deepEqual(analysis(group('one', node('gone'))).preview, [])
})

const profile = (...groups) => editableConfig(config(...groups)).profiles[0]
const connection = (from, to) => ({ source: `app:${from}`, target: `app:${to}` })
const byId = graph => new Map(graph.nodes.map(n => [n.id, n]))
function rejectsUnchanged(p, code, act) {
  const before = structuredClone(p)
  assert.deepEqual(act(), { ok: false, code }); assert.deepEqual(p, before)
}

test('Flow projection uses parent-relative app positions and editable stage edges without serializing graph state', () => {
  const p = profile(group('a', node('a')), { ...group('off'), enabled: false }, { ...group('b', node('b', ['a'])), depends_on: ['a'] })
  p.layout = { 'group:a': { x: -40, y: 27, w: 400, h: 300 }, 'app:a': { x: 29, y: 81, w: 210 } }
  const before = structuredClone(p), graph = toFlowGraph(p, apps('a', 'pool')), nodes = byId(graph)
  assert.deepEqual([...nodes.keys()], ['group:a', 'app:a', 'group:off', 'group:b', 'app:b'])
  const stage = nodes.get('group:a'), child = nodes.get('app:a')
  assert.deepEqual(stage.data, { groupId: 'a' }); assert.equal(stage.type, 'pipelineGroup')
  assert.deepEqual(stage.position, { x: -40, y: 27 }); assert.equal(stage.width, 400); assert.equal(stage.height, 300)
  assert.notEqual(stage.connectable, false); assert.equal(stage.dragHandle, '.group-header')
  assert.deepEqual(child.data, { appId: 'a', groupId: 'a' }); assert.equal(child.type, 'pipelineApp')
  assert.deepEqual(child.position, { x: 29, y: 81 }); assert.equal(child.width, GRAPH_SIZE.appWidth); assert.equal(child.height, GRAPH_SIZE.appHeight)
  assert.equal(child.parentNode, stage.id); assert.equal(child.extent, undefined)
  const signatures = graph.edges.map(e => [e.data.kind, e.source, e.target, e.deletable])
  assert.deepEqual(signatures, [['dependency', 'app:a', 'app:b', true], ['stage', 'group:a', 'group:b', true]])
  for (const e of graph.edges) assert.deepEqual(e.markerEnd, { type: 'arrowclosed' })
  child.position.x = 999; assert.deepEqual(p, before)
})

test('draw and delete modify only the prerequisite; invalid edits leave the draft untouched', () => {
  const p = profile(group('first', node('a'), node('b'), node('c', ['b']), { ...node('off'), enabled: false }), group('last', node('end')))
  const a = p.groups[0].items[0], b = p.groups[0].items[1], before = structuredClone(p)
  const add = (s, t) => applyConnect(p, connection(s, t))
  assert.deepEqual(add('a', 'b'), { ok: true }); assert.deepEqual(b.depends_on, ['a'])
  assert.deepEqual(a, before.groups[0].items[0]); assert.deepEqual(b.readiness, before.groups[0].items[1].readiness)
  rejectsUnchanged(p, 'duplicate', () => add('a', 'b'))
  rejectsUnchanged(p, 'cycle', () => add('c', 'a'))
  rejectsUnchanged(p, 'cycle', () => add('a', 'a'))
  assert.ok(add('end', 'a').ok)
  assert.ok(applyDisconnect(p, connection('end', 'a')).ok)
  rejectsUnchanged(p, 'disabled', () => add('off', 'a'))
  rejectsUnchanged(p, 'missing', () => add('pool', 'a'))
  rejectsUnchanged(p, 'endpoint', () => applyConnect(p, { source: 'group:first', target: 'app:a' }))
  assert.deepEqual(add('b', 'end'), { ok: true })
  const graph = toFlowGraph(p), dep = graph.edges.find(e => e.target === 'app:end')
  const stage = { source: 'group:first', target: 'group:last' }
  assert.ok(applyConnect(p, stage).ok)
  rejectsUnchanged(p, 'cycle', () => applyConnect(p, { source: stage.target, target: stage.source }))
  assert.ok(applyDisconnect(p, stage).ok)
  assert.equal(toFlowGraph(p).edges.some(e => e.data.kind === 'stage'), false)
  assert.deepEqual(applyDisconnect(p, dep), { ok: true }); assert.deepEqual(p.groups[1].items[0].depends_on, [])
  rejectsUnchanged(p, 'missing', () => applyDisconnect(p, dep))
  assert.deepEqual(applyDisconnect(p, connection('a', 'b')), { ok: true }); assert.deepEqual(p, before)
})

test('assignment, stage transfers and explicit index edits preserve fields and synchronize order', () => {
  const p = profile(group('first', node('base')), group('work', node('worker', ['base']), node('sibling')),
    { ...group('off'), enabled: false }, group('last', node('end', ['worker'])), group('after'))
  const worker = p.groups[1].items[0]
  worker.readiness = { type: 'tcp', host: 'localhost', port: 3010, timeout_sec: 9 }; worker.note = 'preserve item metadata'
  p.layout = { 'app:worker': { x: 12, y: 70, w: 239, h: 84 } }
  const move = (id, g, pos, idx) => applyMoveToGroup(p, id, g, pos, idx)
  assert.ok(applyMoveToGroup(structuredClone(p), 'worker', 'after', { x: 0, y: 0 }).ok)
  rejectsUnchanged(p, 'disabled', () => move('worker', 'off', { x: 0, y: 0 }))
  rejectsUnchanged(p, 'index', () => move('worker', 'work', undefined, 7))
  rejectsUnchanged(p, 'position', () => move('worker', 'work', { x: Infinity, y: 0 }))
  assert.deepEqual(move('worker', 'work', { x: 26, y: 80 }), { ok: true }); assert.equal(p.groups[1].items[0], worker)
  assert.deepEqual(p.layout['app:worker'], { x: 26, y: 80, w: 239, h: 84 })
  assert.deepEqual(move('worker', 'work', undefined, 1), { ok: true }); assert.equal(p.groups[1].items[1], worker)
  assert.deepEqual(move('worker', 'first', { x: 41, y: 82 }, 0), { ok: true }); assert.equal(p.groups[0].items[0], worker)
  assert.deepEqual(worker.depends_on, ['base']); assert.equal(worker.note, 'preserve item metadata'); assert.equal(worker.readiness.port, 3010)
  assert.deepEqual(move('pool', 'work', { x: 15, y: 88 }), { ok: true }); assert.deepEqual(p.groups[1].items[1], { ...newNode('pool'), order: 1 })
  assert.deepEqual(p.groups.flatMap(g => g.items.map(n => [n.app_id, n.order])), [['worker', 0], ['base', 1], ['sibling', 0], ['pool', 1], ['end', 0]])
  assert.ok(applyGroupOrder(structuredClone(p), 'last', 0).ok)
  assert.deepEqual(applyGroupOrder(p, 'work', 0), { ok: true }); assert.deepEqual(p.groups.map(g => [g.id, g.order]),
    [['work', 0], ['first', 1], ['off', 2], ['last', 3], ['after', 4]])
  assert.deepEqual(move('worker', 'last'), { ok: true })
  assert.deepEqual(p.layout['app:worker'], { x: 41, y: 82, w: 239, h: 84 })
})

test('auto-layout aligns parallel batches, packs stages, and derives only missing sequential arrows', () => {
  const p = profile({ ...group('seq', node('a', ['b']), node('b'), node('c'), { ...node('d'), enabled: false }), mode: 'sequential' },
    group('parallel', node('p', ['q']), node('q'), node('r')), group('empty'))
  const expected = toFlowGraph(p)
  p.layout = { 'app:b': { x: 801, y: 602, w: 260, h: 400 }, 'group:seq': { x: 9, y: 9, w: 4000, h: 3000 }, 'app:pool': { x: 10, y: 10 } }
  const { layout: ignored, ...model } = structuredClone(p)
  assert.deepEqual(applyAutoLayout(p), { ok: true }); assert.deepEqual(model, { name: p.name, on_failure: p.on_failure, groups: p.groups })
  const graph = toFlowGraph(p), nodes = byId(graph), rect = id => nodes.get(id)
  assert.deepEqual(p.layout, Object.fromEntries(expected.nodes.map(n => [n.id, n.position])))
  assert.deepEqual(graph, expected)
  assert.ok(rect('app:b').position.x + GRAPH_SIZE.appWidth < rect('app:a').position.x); assert.ok(rect('app:a').position.x < rect('app:c').position.x)
  assert.equal(rect('app:q').position.x, rect('app:r').position.x); assert.ok(rect('app:q').position.y < rect('app:r').position.y)
  assert.ok(rect('app:p').position.x > rect('app:q').position.x)
  assert.ok(rect('group:parallel').position.x > rect('group:seq').width + rect('group:seq').position.x)
  const sequence = graph.edges.filter(e => e.data.kind === 'sequence')
  assert.deepEqual(sequence.map(e => [e.source, e.target, e.deletable]), [['app:a', 'app:c', false]])
  rejectsUnchanged(p, 'derived', () => applyDisconnect(p, sequence[0]))
  // A sequence arrow is a scheduling consequence, never a prerequisite in cycle checks.
  assert.deepEqual(applyConnect(p, connection('c', 'a')), { ok: true })
  assert.deepEqual(toFlowGraph(p).edges.filter(e => e.data.kind === 'sequence').map(e => [e.source, e.target]), [['app:b', 'app:c']])
  assert.deepEqual(applyDisconnect(p, connection('c', 'a')), { ok: true })
  assert.deepEqual(applyConnect(p, connection('a', 'c')), { ok: true })
  assert.equal(toFlowGraph(p).edges.find(e => e.source === 'app:a' && e.target === 'app:c').data.kind, 'dependency')
  const once = structuredClone(p); assert.deepEqual(applyAutoLayout(p), { ok: true }); assert.deepEqual(p, once)
})

test('sequential arbitration across rank words matches executable preview, not FIFO wave order', () => {
  const items = Array.from({ length: 1090 }, (_, i) => node(`n${i}`, i % 3 === 0 && i + 2 < 1090 ? [`n${i + 2}`] : []))
  const p = profile({ ...group('big', ...items), mode: 'sequential' })
  const order = toFlowGraph(p).nodes.filter(n => n.type === 'pipelineApp').map(n => n.data.appId)
  assert.deepEqual(order, analyzeProfile(p, items).preview[0].batches.flat())
})

test('an app dropped outside all groups stays at its drop point and expands its own group', async () => {
  const { usePipelineCanvas } = await import('../aivudaos/resources/ui/src/composables/usePipelineCanvas.js')
  for (const drop of [{ x: -100, y: -50 }, { x: 700, y: 350 }]) {
    const p = profile(group('g', node('a'), node('b')))
    p.layout = { 'group:g': { x: 80, y: 120 } }
    const canvas = usePipelineCanvas({ profile: { value: p }, profileProgress: { value: null }, locked: { value: false },
      changed: () => canvas.refresh(), resumeSave() {} })
    canvas.refresh()
    const before = byId({ nodes: canvas.nodes.value }), parent = before.get('group:g')
    const point = (group, offset) => ({ x: group.position.x + offset.x, y: group.position.y + offset.y })
    canvas.onDragStop({ node: { ...before.get('app:a'), position: drop, dimensions: { width: 200, height: 76 } } })
    const after = byId({ nodes: canvas.nodes.value }), expanded = after.get(parent.id), moved = after.get('app:a')
    assert.equal(moved.parentNode, parent.id)
    assert.deepEqual(point(expanded, moved.position), point(parent, drop))
    assert.deepEqual(point(expanded, after.get('app:b').position), point(parent, before.get('app:b').position))
    assert.ok(moved.position.x >= 0 && moved.position.y >= GRAPH_SIZE.header)
    assert.ok(expanded.width >= moved.position.x + moved.width && expanded.height >= moved.position.y + moved.height)
  }
})

test('node status uses live running state after completion and preserves unresolved exceptions', () => {
  assert.equal(pipelineNodeStatus(true, 'waiting_ready', true, true), 'waiting_ready')
  assert.equal(pipelineNodeStatus(true, 'active', true, false), 'active')
  assert.equal(pipelineNodeStatus(false, 'active', true, false), 'idle')
  assert.equal(pipelineNodeStatus(false, 'completed', true, false), 'completed')
  assert.equal(pipelineNodeStatus(false, 'stopped', true, true), 'running')
  assert.equal(pipelineNodeStatus(false, 'starting', false, false), 'disabled')
  for (const status of ['failed', 'degraded', 'skipped']) assert.equal(pipelineNodeStatus(false, status, true, true), status)
  assert.equal(pipelineNodeStatus(false, undefined, true, true), 'running')
})

test('animated edges derive transient activity from the matching node or stage operation statuses', () => {
  const p = profile(group('up', node('up')), { ...group('down', node('down', ['up'])), depends_on: ['up'] })
  const graph = toFlowGraph(p), dependency = graph.edges.find(e => e.data.kind === 'dependency'), stage = graph.edges.find(e => e.data.kind === 'stage')
  const state = newProgress({ operation_id: 'run' })
  state.nodes.set('up', 'active'); state.nodes.set('down', 'waiting_ready')
  assert.equal(isEdgeAnimated(dependency, state), true); assert.equal(isEdgeAnimated(stage, state), false)
  assert.equal(isEdgeAnimated(dependency, { nodes: { up: 'ready', down: 'waiting' } }), true)
  state.nodes.set('up', 'completed'); assert.equal(isEdgeAnimated(dependency, state), true)
  state.stages.set('up', 'active'); state.stages.set('down', 'starting'); assert.equal(isEdgeAnimated(stage, state), true)
  state.nodes.set('down', 'active'); assert.equal(isEdgeAnimated(dependency, state), false)
  state.nodes.set('up', 'degraded'); state.nodes.set('down', 'starting'); assert.equal(isEdgeAnimated(dependency, state), false)
  state.done = true; assert.equal(isEdgeAnimated(stage, state), false); assert.equal(isEdgeAnimated(dependency, null), false)
  assert.deepEqual(graph, toFlowGraph(p)); assert.ok(!('layout' in p) && !('edges' in p))
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


test('an older backend rejecting group dependencies gives a retryable upgrade message', () => {
  const message = "config.profiles[0].groups[1] contains an unknown field: 'depends_on'; config.default_profile must name an existing profile"
  assert.equal(pipelineSaveError({ status: 422, message }, key => key), 'pipeline.updateBackendForGroups')
  assert.equal(pipelineSaveError({ status: 422, message: 'Dependency cycle' }, key => key), 'Dependency cycle')
})
