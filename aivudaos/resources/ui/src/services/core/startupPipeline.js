// Keep the wire format in the editor: profiles, groups and items are ordered arrays.
export function createStartupPipelineApi(request) {
  const base = '/api/apps/pipeline'
  const call = (suffix, method, body) => request(base + suffix, { auth: true, method, body })
  return {
    load: () => call('', 'GET'),
    save: config => call('', 'PUT', config),
    validate: config => call('/validate', 'POST', config),
    run: scope => call('/run', 'POST', scope),
    stop: scope => call('/stop', 'POST', scope),
  }
}

export const ros2Stages = [
  ['middleware', 'Middleware & Transport'], ['hardware', 'Hardware & Drivers'],
  ['perception', 'Perception & Localization'], ['planning', 'Planning & Control'],
  ['telemetry', 'Telemetry & Tools'],
]
export const failurePolicies = ['abort', 'skip_dependents', 'continue']
export const readinessFields = {
  started: [], delay: ['delay_sec'], tcp: ['host', 'port'], http: ['url'],
  ros2_node: ['node_name'], ros2_topic: ['topic', 'require_publisher'],
  ros2_lifecycle: ['node_name', 'lifecycle_state'], command: ['command'],
}
export const cloneConfig = config => JSON.parse(JSON.stringify(config))
export const newNode = app_id => ({ app_id, order: 0, enabled: true, depends_on: [], readiness: { type: 'started' } })
export const newGroup = (id, name) => ({ id, name, order: 0, enabled: true, mode: 'parallel', items: [] })
export function newReadiness(type) {
  const defaults = { delay_sec: 1, host: '127.0.0.1', port: null, url: '', node_name: '',
    topic: '', require_publisher: false, lifecycle_state: 'active', command: '' }
  const result = { type }
  for (const field of readinessFields[type] || []) result[field] = defaults[field]
  if (type !== 'started') Object.assign(result, { timeout_sec: 30, interval_sec: 1 })
  return result
}

export function normalizeOrder(groups) {
  groups.forEach((group, index) => {
    group.order = index
    group.items.forEach((item, i) => { item.order = i })
  })
  return groups
}
export function editableConfig(config) {
  const result = cloneConfig(config)
  const byOrder = (a, b) => (a.order ?? 0) - (b.order ?? 0)
  for (const profile of result.profiles) {
    profile.groups.sort(byOrder)
    for (const group of profile.groups) group.items.sort(byOrder)
    normalizeOrder(profile.groups)
  }
  return result
}
export function applyRos2Template(profile) {
  const remaining = new Map(profile.groups.map(g => [g.id, g]))
  const standard = ros2Stages.map(([id, name]) => {
    const group = remaining.get(id) || newGroup(id, name)
    remaining.delete(id)
    return group
  })
  profile.groups = normalizeOrder([...standard, ...remaining.values()])
}
export function unassignedNodes(profile, installed) {
  const assigned = new Set(profile.groups.flatMap(g => g.items.map(n => n.app_id)))
  return installed.filter(app => !assigned.has(app.app_id)).map(app => newNode(app.app_id))
}

// Check the draft immediately after a move. Do not silently remove or invert an edge.
// The server independently validates the entire config (including probe parameters).
export function analyzeProfile(profile, installed) {
  const errors = [], preview = [], nodes = new Map(), state = new Map(), stack = []
  const ids = new Set(installed.map(a => a.app_id))
  const issue = (code, apps, dependency) => errors.push({ code, apps, dependency })
  profile.groups.forEach((group, stage) => group.items.forEach(node => {
    const id = node.app_id
    if (nodes.has(id)) issue('duplicate', [id])
    if (!ids.has(id)) issue('notInstalled', [id])
    nodes.set(id, { stage, node, active: group.enabled !== false && node.enabled !== false })
  }))
  function visit(id) {
    state.set(id, 1); stack.push(id)
    const entry = nodes.get(id)
    for (const dep of entry.node.depends_on || []) {
      const upstream = nodes.get(dep)
      if (!upstream) { issue('missing', [id], dep); continue }
      if (upstream.stage > entry.stage) issue('reverse', [id, dep], dep)
      if (entry.active && !upstream.active) issue('disabled', [id, dep], dep)
      if (state.get(dep) === 1) issue('cycle', stack.slice(stack.indexOf(dep)), dep)
      else if (!state.has(dep)) visit(dep)
    }
    stack.pop(); state.set(id, 2)
  }
  for (const id of nodes.keys()) if (!state.has(id)) visit(id)
  if (!errors.length) for (const group of profile.groups.filter(g => g.enabled !== false)) {
    const pending = new Set(group.items.filter(n => n.enabled !== false).map(n => n.app_id))
    const batches = []
    while (pending.size) {
      const ready = [...pending].filter(id => !(nodes.get(id).node.depends_on || []).some(dep => pending.has(dep)))
      const batch = group.mode === 'sequential' ? ready.slice(0, 1) : ready
      if (!batch.length) break
      batches.push(batch)
      batch.forEach(id => pending.delete(id))
    }
    preview.push({ group_id: group.id, batches })
  }
  return { errors, preview }
}

export function newProgress(operation) {
  return { ...operation, status: operation.status || 'queued', seq: 0, nodes: new Map(), stages: new Map(), logs: [], done: false }
}
export function applyOperationEvent(progress, event) {
  if (!event || (event.operation_id && event.operation_id !== progress.operation_id) || progress.done) return
  if (event.seq && event.seq <= progress.seq) return // SSE replays history on reconnect.
  if (event.seq) progress.seq = event.seq
  if (event.type === 'pipeline_node') progress.nodes.set(event.app_id, event.status)
  if (event.type === 'pipeline_stage') progress.stages.set(event.group_id, event.status)
  if (event.type === 'log' || event.type === 'error' || (event.done && event.error)) {
    const line = event.message || event.error || event.line
    if (line) progress.logs.push(line)
    if (progress.logs.length > 300) progress.logs.shift()
  }
  if (['status', 'completed', 'error'].includes(event.type) && event.status) progress.status = event.status
  progress.done = !!event.done || event.type === 'completed'
}
