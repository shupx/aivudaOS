import { graphIssue } from './pipelineDependencies.js'
import { deepClone } from './configTransfer.js'

// Keep the wire format in the editor: profiles, groups and items are ordered arrays.
export function createStartupPipelineApi(request) {
  const base = '/api/apps/pipeline'
  const call = (suffix, method, body) => request(base + suffix, { auth: true, method, body })
  return {
    load: () => call('', 'GET'),
    loadForList: () => call('?view=list', 'GET'),
    save: config => call('', 'PUT', config),
    validate: config => call('/validate', 'POST', config),
    run: scope => call('/run', 'POST', scope),
    restart: scope => call('/restart', 'POST', scope),
    stop: scope => call('/stop', 'POST', scope),
  }
}

export function pipelineSaveError(error, t) {
  if (error.status === 422 && /config\.profiles\[\d+\]\.groups\[\d+\] contains an unknown field: 'depends_on'/.test(error.message)) {
    return t('pipeline.updateBackendForGroups')
  }
  return error.message
}

export const ros2Stages = [
  ['middleware', 'Middleware & Transport'], ['hardware', 'Hardware & Drivers'],
  ['perception', 'Perception & Localization'], ['planning', 'Planning & Control'],
  ['telemetry', 'Telemetry & Tools'],
]
export function pipelineGroupLabel(group, t) {
  if (!group) return ''
  const templateName = ros2Stages.some(([id, name]) => group.id === id && group.name === name)
  return templateName ? t(`pipeline.stages.${group.id}`) : group.name
}
export const failurePolicies = ['abort', 'skip_dependents', 'continue']
export const readinessFields = {
  started: [], delay: ['delay_sec'], tcp: ['host', 'port'], http: ['url'],
  ros2_node: ['node_name'], ros2_topic: ['topic', 'require_publisher', 'require_message'],
  log_contains: ['pattern'], log_regex: ['pattern'], exited_zero: [],
  ros2_lifecycle: ['node_name', 'lifecycle_state'], command: ['command'],
}
export const cloneConfig = deepClone
export const newNode = app_id => ({ app_id, order: 0, enabled: true, depends_on: [], readiness: { type: 'started' } })
export const newGroup = (id, name) => ({ id, name, order: 0, enabled: true, mode: 'parallel', depends_on: [], items: [] })
export function newReadiness(type) {
  const defaults = { delay_sec: 1, host: '127.0.0.1', port: null, url: '', node_name: '',
    pattern: '', require_message: false, topic: '', require_publisher: false, lifecycle_state: 'active', command: '' }
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
  for (const profile of result.profiles) {
    profile.groups = normalizeOrder(orderedGroups(profile.groups))
  }
  return result
}
export function applyRos2Template(profile) {
  const remaining = new Map(profile.groups.map(g => [g.id, g]))
  const added = new Set()
  const standard = ros2Stages.map(([id, name]) => {
    if (!remaining.has(id)) added.add(id)
    const group = remaining.get(id) || newGroup(id, name)
    remaining.delete(id)
    return group
  })
  profile.groups = normalizeOrder([...standard, ...remaining.values()])
  for (let i = 1; i < standard.length; i++) {
    const group = standard[i]
    if (!added.has(group.id)) continue
    group.depends_on.push(standard[i - 1].id)
    if (graphIssue(profile.groups)) group.depends_on.pop()
  }
}
// The editor writes ranked arrays in order. External configs may use unsorted,
// negative or sparse integer ranks. Stable byte buckets keep projection linear
// even then, without allocating an array as large as the largest rank.
function inPipelineOrder(rows) {
  if (rows.every((row, i) => i === 0 || (rows[i - 1].order ?? 0) <= (row.order ?? 0))) return rows
  const bytes = new DataView(new ArrayBuffer(8))
  let sorted = rows
  for (let byte = 7; byte >= 0; byte--) {
    const buckets = Array.from({ length: 256 }, () => [])
    for (const row of sorted) {
      const order = row.order || 0 // Includes -0 as the same rank as 0.
      bytes.setFloat64(0, order) // Big-endian IEEE 754, least significant byte first.
      const bits = bytes.getUint8(byte)
      const key = order < 0 ? 255 - bits : byte === 0 ? bits + 128 : bits
      buckets[key].push(row)
    }
    sorted = buckets.flat()
  }
  return sorted
}

function orderedGroups(groups) {
  const legacy = !groups.some(group => Array.isArray(group.depends_on))
  let previous = []
  return inPipelineOrder(groups).map(group => {
    const depends_on = group.depends_on ?? (legacy && group.enabled !== false ? previous : [])
    if (legacy && group.enabled !== false) previous = [group.id]
    return { ...group, depends_on, items: inPipelineOrder(group.items || []) }
  })
}

export function listStageStatus(operation, profileName, groupId) {
  if (!operation || operation.profile !== profileName) return ''
  const stage = operation.stages.get(groupId)
  if (operation.group_id === groupId) return stage || operation.status
  return stage === 'starting' || stage === 'stopping' ? stage : ''
}

export function prepareAppListGroups(config) {
  const profile = config?.profiles?.find(profile => profile.name === config.default_profile)
  return orderedGroups(profile?.groups || []).map(group => {
    const nodeSummaries = new Map()
    for (const item of group.items) {
      nodeSummaries.set(item.app_id, {
        enabled: item.enabled !== false,
        readiness: item.readiness || { type: 'started' },
        depends_on: item.depends_on || [],
      })
    }
    return { id: group.id, name: group.name, order: group.order ?? 0, mode: group.mode || 'parallel',
      depends_on: group.depends_on, enabled: group.enabled !== false, nodeSummaries }
  })
}

export function joinAppListInventory(apps, preparedGroups) {
  const remaining = new Map(apps.map(app => [app.app_id, app]))
  const groups = preparedGroups.map(group => {
    const groupedApps = []
    let runningCount = 0
    for (const id of group.nodeSummaries.keys()) {
      const app = remaining.get(id)
      if (!app) continue
      remaining.delete(id)
      groupedApps.push(app)
      if (app.running) runningCount++
    }
    return { ...group, apps: groupedApps, runningCount }
  })
  return { groups, unassignedApps: [...remaining.values()] }
}

export function buildAppListGroups(apps, pipelineConfig) {
  return joinAppListInventory(apps, prepareAppListGroups(pipelineConfig))
}

export function unassignedNodes(profile, installed) {
  const assigned = new Set(profile.groups.flatMap(g => g.items.map(n => n.app_id)))
  return installed.filter(app => !assigned.has(app.app_id)).map(app => newNode(app.app_id))
}

// Check the draft immediately after a move. Do not silently remove or invert an edge.
// The server independently validates the entire config (including probe parameters).
export function profileIssues(profile, installed) {
  const installedIds = new Set(installed.map(a => a.app_id))
  const errors = profile.groups.flatMap(g => g.items.filter(n => !installedIds.has(n.app_id))
    .map(n => ({ code: 'notInstalled', apps: [n.app_id] })))
  const issue = graphIssue(profile.groups)
  if (issue) errors.unshift(issue)
  return errors
}

export function newProgress(operation) {
  return { ...operation, status: operation.status || 'queued', seq: 0, nodes: new Map(), stages: new Map(), logs: [], done: false }
}
export function applyOperationEvent(progress, event) {
  if (!event || (event.operation_id && event.operation_id !== progress.operation_id) || progress.done) return false
  if (event.seq && event.seq <= progress.seq) return false // SSE replays history on reconnect.
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
  return true
}
