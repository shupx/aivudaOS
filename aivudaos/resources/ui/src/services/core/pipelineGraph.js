import { graphIssue, schedule } from './pipelineDependencies.js'
// A projection of an editableConfig profile (arrays are already in execution rank order).
// Nothing here stores Flow nodes or edges in the execution model.
import { newNode, normalizeOrder } from './startupPipeline.js'

export const GRAPH_SIZE = Object.freeze({ appWidth: 200, appHeight: 76, groupWidth: 272, groupHeight: 180,
  padding: 24, header: 64, columnGap: 48, rowGap: 20, stageGap: 64 })

const appKey = id => `app:${id}`
const groupKey = id => `group:${id}`
const ok = () => ({ ok: true })
const fail = code => ({ ok: false, code })
const validPosition = p => Number.isFinite(p?.x) && Number.isFinite(p?.y)
const validIndex = (index, end) => Number.isInteger(index) && index >= 0 && index <= end
export const findGroup = (groups, id) => groups.find(g => g.items.some(n => n.app_id === id))
const findItem = (group, id) => group?.items.find(n => n.app_id === id)
const size = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback

function edge(kind, source, target) {
  const editable = kind !== 'sequence'
  return { id: `${kind}:${source}:${target}`, source, target, data: { kind },
    class: editable ? '' : 'pipeline-derived-edge', selectable: editable, focusable: editable,
    deletable: editable, markerEnd: { type: 'arrowclosed' } }
}

function box(saved, x, y, w, h) {
  return { x: validPosition(saved) ? saved.x : x, y: validPosition(saved) ? saved.y : y,
    w: size(saved?.w, w), h: size(saved?.h, h) }
}

function flowNode(id, type, data, { x, y, w, h }) {
  return { id, type, data, position: { x, y }, width: w, height: h,
    style: { width: `${w}px`, height: `${h}px` }, deletable: false }
}

// Assigned apps stay visible even after uninstall so a broken profile can be repaired.
export function toFlowGraph(profile) {
  const layout = profile?.layout || {}, nodes = [], edges = [], assigned = new Set(), s = GRAPH_SIZE
  for (const g of profile?.groups || []) for (const item of g.items) assigned.add(item.app_id)
  let stageX = 0
  for (const group of profile?.groups || []) {
    const id = groupKey(group.id), children = []
    const { batches, unscheduled, sequentialPredecessors, cycle } = schedule(group)
    let columnX = s.padding, right = 0, bottom = 0
    for (const batch of [...batches, unscheduled]) {
      let rowY = s.header, columnWidth = 0
      for (const item of batch) {
        const key = appKey(item.app_id), deps = item.depends_on || []
        const rect = { ...box(layout[key], columnX, rowY, s.appWidth, s.appHeight), w: s.appWidth, h: s.appHeight }
        children.push({ ...flowNode(key, 'pipelineApp', { appId: item.app_id, groupId: group.id }, rect), parentNode: id })
        rowY = Math.max(rowY, rect.y) + rect.h + s.rowGap
        columnWidth = Math.max(columnWidth, rect.x + rect.w - columnX)
        right = Math.max(right, rect.x + rect.w); bottom = Math.max(bottom, rect.y + rect.h)
        for (const dep of deps) if (assigned.has(dep)) edges.push(edge('dependency', appKey(dep), key))
        const previous = sequentialPredecessors.get(item)
        if (!cycle && group.enabled !== false && previous !== undefined && !deps.includes(previous)) {
          edges.push(edge('sequence', appKey(previous), key))
        }
      }
      columnX += columnWidth + s.columnGap
    }
    const rect = box(layout[id], stageX, 0, s.groupWidth, s.groupHeight)
    rect.w = Math.max(rect.w, right + s.padding); rect.h = Math.max(rect.h, bottom + s.padding)
    nodes.push({ ...flowNode(id, 'pipelineGroup', { groupId: group.id }, rect), dragHandle: '.group-header' })
    for (const child of children) nodes.push(child) // Parents must precede their children in Flow.
    for (const dep of group.depends_on || []) edges.push(edge('stage', groupKey(dep), id))
    stageX = Math.max(stageX, rect.x + rect.w + s.stageGap)
  }
  return { nodes, edges }
}

export function applyAutoLayout(profile, graph = toFlowGraph({ groups: profile.groups })) {
  const layout = {}
  for (const { id, position } of graph.nodes) layout[id] = { ...position }
  profile.layout = layout
  return ok()
}

export function pipelineNodeStatus(active, status, enabled, running) {
  if (status && (active || ['failed', 'degraded', 'skipped', 'completed'].includes(status))) return status
  if (!enabled) return 'disabled'
  return running ? 'running' : 'idle'
}

// Validate a shallow candidate before touching any mutable (possibly reactive) array.
function issue(groups) { return graphIssue(groups)?.code }

function groupConnection(profile, connection, remove) {
  const from = connection.source.slice(6), to = connection.target.slice(6)
  const target = profile.groups.find(g => g.id === to)
  if (!target || !profile.groups.some(g => g.id === from)) return fail('missing')
  const current = target.depends_on || []
  if (remove && !current.includes(from)) return fail('missing')
  if (!remove && current.includes(from)) return fail('duplicate')
  const depends_on = remove ? current.filter(id => id !== from) : [...current, from]
  if (!remove) {
    const error = issue(profile.groups.map(g => g === target ? { ...g, depends_on } : g))
    if (error) return fail(error)
  }
  target.depends_on = depends_on
  return ok()
}

function appEnds(connection) {
  return [connection?.source, connection?.target].map(key =>
    typeof key === 'string' && key.startsWith('app:') ? key.slice(4) : '')
}

export function applyConnect(profile, connection) {
  if (connection?.source?.startsWith('group:') && connection.target?.startsWith('group:')) return groupConnection(profile, connection, false)
  const [from, to] = appEnds(connection), groups = profile.groups
  if (!from || !to) return fail('endpoint')
  const target = findGroup(groups, to), item = findItem(target, to)
  if (!item || !findGroup(groups, from)) return fail('missing')
  if (from === to) return fail('cycle')
  if (item.depends_on?.includes(from)) return fail('duplicate')
  const deps = [...(item.depends_on || []), from]
  const candidate = groups.map(g => g !== target ? g : { ...g,
    items: g.items.map(n => n !== item ? n : { ...n, depends_on: deps }) })
  const error = issue(candidate)
  if (error) return fail(error)
  item.depends_on = deps
  return ok()
}

export function applyDisconnect(profile, connection) {
  if (connection?.source?.startsWith('group:') && connection.target?.startsWith('group:')) return groupConnection(profile, connection, true)
  if (connection?.data?.kind && connection.data.kind !== 'dependency') return fail('derived')
  const [from, to] = appEnds(connection)
  if (!from || !to) return fail('endpoint')
  const item = findItem(findGroup(profile.groups, to), to)
  if (!item?.depends_on?.includes(from)) return fail('missing')
  item.depends_on = item.depends_on.filter(dep => dep !== from)
  return ok()
}

export function applyMoveToGroup(profile, appId, groupId, position, index) {
  const groups = profile.groups, to = groups.find(g => g.id === groupId), from = findGroup(groups, appId)
  if (!to || typeof appId !== 'string' || !appId || !/^[\w.-]+$/.test(appId) || ['.', '..'].includes(appId)) return fail('missing')
  if (position != null && !validPosition(position)) return fail('position')
  const item = findItem(from, appId) || newNode(appId) // Caller admits new items only from installed pool.
  const end = to.items.length - Number(from === to)
  const at = index ?? (from === to ? from.items.indexOf(item) : end)
  if (!validIndex(at, end)) return fail('index')
  if (from !== to || from.items.indexOf(item) !== at) {
    const items = to.items.filter(n => n !== item)
    items.splice(at, 0, item)
    const left = from && from !== to ? from.items.filter(n => n !== item) : null
    const candidate = groups.map(g => g === to ? { ...g, items } : g === from ? { ...g, items: left } : g)
    const error = issue(candidate)
    if (error) return fail(error)
    if (left) from.items = left
    to.items = items
    normalizeOrder(groups)
  }
  const key = appKey(appId)
  if (position) {
    const layout = profile.layout ??= {}
    layout[key] = { ...layout[key], x: position.x, y: position.y }
  } // Without a drop point, keep the saved offset and size relative to the new parent.
  return ok()
}

export function applyGroupOrder(profile, groupId, index) {
  const groups = [...profile.groups], from = groups.findIndex(g => g.id === groupId)
  if (from < 0) return fail('missing')
  if (!validIndex(index, groups.length - 1)) return fail('index')
  const [group] = groups.splice(from, 1)
  groups.splice(index, 0, group)
  const error = issue(groups)
  if (error) return fail(error)
  profile.groups = normalizeOrder(groups)
  return ok()
}

export function isEdgeAnimated(edge, statuses) {
  if (!statuses || statuses.done) return false
  const stage = edge?.data?.kind === 'stage', prefix = stage ? 'group:' : 'app:'
  const states = stage ? statuses.stages : statuses.nodes
  const state = id => {
    if (!id?.startsWith(prefix)) return undefined
    const key = id.slice(prefix.length)
    return states instanceof Map ? states.get(key) : states?.[key]
  }
  return ['active', 'completed', 'ready'].includes(state(edge?.source)) &&
    ['starting', 'waiting_ready', 'waiting'].includes(state(edge?.target))
}
