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
const findGroup = (groups, id) => groups.find(g => g.items.some(n => n.app_id === id))
const findItem = (group, id) => group?.items.find(n => n.app_id === id)
const size = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback

// A newly ready item can precede every item already waiting. Select the lowest rank
// without rescanning the queue or sorting. Each summary bit denotes a nonempty word
// below it; at most seven 32-bit levels cover every possible JavaScript array index.
function rankedQueue(count) {
  const levels = []
  do { count = Math.ceil(count / 32); levels.push(new Uint32Array(count || 1)) } while (count > 1)
  return {
    add(rank) {
      for (const words of levels) {
        const word = rank >>> 5, old = words[word]
        words[word] |= 1 << (rank & 31)
        if (old) break
        rank = word
      }
    },
    take() {
      if (!levels[levels.length - 1][0]) return undefined
      let rank = 0
      for (let k = levels.length - 1; k >= 0; k--) {
        const bits = levels[k][rank]
        rank = rank * 32 + (31 - Math.clz32(bits & -bits))
      }
      let cursor = rank
      for (const words of levels) {
        const word = cursor >>> 5
        words[word] &= ~(1 << (cursor & 31))
        if (words[word]) break
        cursor = word
      }
      return rank
    },
  }
}

// Kahn traversal, ignoring cross-stage dependencies already satisfied by a barrier.
// Parallel items of equal depth retain array order; sequential items use ready rank.
function schedule(group) {
  const items = group.items, serial = group.mode === 'sequential'
  const rank = new Map(items.map((item, i) => [item.app_id, i]))
  const waiting = items.map(() => 0), next = items.map(() => []), depth = items.map(() => 0)
  const batches = [], ready = [], ranked = serial ? rankedQueue(items.length) : null
  const enqueue = i => serial ? ranked.add(i) : ready.push(i)
  items.forEach((item, i) => {
    for (const dep of item.depends_on || []) if (rank.has(dep)) {
      next[rank.get(dep)].push(i); waiting[i]++
    }
  })
  waiting.forEach((n, i) => { if (!n) enqueue(i) })
  let visited = 0, cursor = 0
  for (let i; (i = serial ? ranked.take() : ready[cursor++]) !== undefined;) {
    visited++
    if (serial && items[i].enabled !== false) batches.push([items[i]])
    for (const j of next[i]) {
      depth[j] = Math.max(depth[j], depth[i] + 1)
      if (--waiting[j] === 0) enqueue(j)
    }
  }
  const unscheduled = []
  items.forEach((item, i) => {
    if (waiting[i] || item.enabled === false) unscheduled.push(item)
    else if (!serial) (batches[depth[i]] ??= []).push(item)
  })
  return { batches: batches.filter(Boolean), unscheduled, cycle: visited !== items.length }
}

function edge(kind, source, target) {
  const editable = kind === 'dependency'
  return { id: `${kind}:${source}:${target}`, source, target, data: { kind },
    class: editable ? '' : 'pipeline-derived-edge', selectable: editable, focusable: editable,
    deletable: editable, markerEnd: { type: 'arrowclosed' } }
}

function box(saved, x, y, w, h, automatic) {
  return { x: !automatic && validPosition(saved) ? saved.x : x, y: !automatic && validPosition(saved) ? saved.y : y,
    w: size(saved?.w, w), h: size(saved?.h, h) }
}

function flowNode(id, type, data, { x, y, w, h }) {
  return { id, type, data, position: { x, y }, width: w, height: h,
    style: { width: `${w}px`, height: `${h}px` }, deletable: false }
}

function project(profile, automatic) {
  const nodes = [], edges = [], assigned = new Set(), layout = profile?.layout || {}, s = GRAPH_SIZE
  for (const g of profile?.groups || []) for (const item of g.items) assigned.add(item.app_id)
  let stageX = 0, previousGroup
  for (const group of profile?.groups || []) {
    const id = groupKey(group.id), { batches, unscheduled, cycle } = schedule(group), children = []
    let previousApp, columnX = s.padding, right = 0, bottom = 0
    for (const batch of [...batches, unscheduled]) {
      let rowY = s.header, columnWidth = 0
      for (const item of batch) {
        const key = appKey(item.app_id), deps = item.depends_on || []
        const rect = box(layout[key], columnX, rowY, s.appWidth, s.appHeight, automatic)
        children.push({ ...flowNode(key, 'pipelineApp', { appId: item.app_id, groupId: group.id }, rect), parentNode: id })
        rowY = Math.max(rowY, rect.y) + rect.h + s.rowGap
        columnWidth = Math.max(columnWidth, rect.x + rect.w - columnX)
        right = Math.max(right, rect.x + rect.w); bottom = Math.max(bottom, rect.y + rect.h)
        for (const dep of deps) if (assigned.has(dep)) edges.push(edge('dependency', appKey(dep), key))
        if (!cycle && group.enabled !== false && group.mode === 'sequential' && batch !== unscheduled) {
          if (previousApp !== undefined && !deps.includes(previousApp)) edges.push(edge('sequence', appKey(previousApp), key))
          previousApp = item.app_id
        }
      }
      columnX += columnWidth + s.columnGap
    }
    const rect = box(layout[id], stageX, 0, s.groupWidth, s.groupHeight, automatic)
    rect.w = Math.max(rect.w, right + s.padding); rect.h = Math.max(rect.h, bottom + s.padding)
    nodes.push({ ...flowNode(id, 'pipelineGroup', { groupId: group.id }, rect), connectable: false, dragHandle: '.group-header' })
    for (const child of children) nodes.push(child) // Parents must precede their children in Flow.
    if (group.enabled !== false) {
      if (previousGroup) edges.push(edge('stage', previousGroup, id))
      previousGroup = id
    }
    stageX = Math.max(stageX, rect.x + rect.w + s.stageGap)
  }
  return { nodes, edges }
}

// Inventory membership determines the external pool, not the graph: even an assigned
// but uninstalled app has to remain visible so an invalid profile can be repaired.
export function toFlowGraph(profile, _installedApps) {
  return project(profile, false)
}

export function applyAutoLayout(profile) {
  const layout = {}, previous = profile.layout || {}
  for (const { id, position } of project(profile, true).nodes) {
    layout[id] = { ...previous[id], ...position }
  }
  profile.layout = layout
  return ok()
}

// Validate a shallow candidate before touching any mutable (possibly reactive) array.
function issue(groups) {
  const owners = new Map(), stages = new Set()
  for (const [stage, group] of groups.entries()) {
    if (stages.has(group.id)) return 'duplicate'
    stages.add(group.id)
    for (const item of group.items) {
      if (owners.has(item.app_id)) return 'duplicate'
      owners.set(item.app_id, { item, stage, enabled: group.enabled !== false && item.enabled !== false })
    }
  }
  for (const { item, stage, enabled } of owners.values()) for (const dep of item.depends_on || []) {
    const source = owners.get(dep)
    if (!source) return 'missing'
    if (source.stage > stage) return 'reverse'
    if (enabled && !source.enabled) return 'disabled'
  }
  if (groups.some(g => schedule(g).cycle)) return 'cycle'
}

function appEnds(connection) {
  return [connection?.source, connection?.target].map(key =>
    typeof key === 'string' && key.startsWith('app:') ? key.slice(4) : '')
}

export function applyConnect(profile, connection) {
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
  return ['active', 'ready'].includes(state(edge?.source)) &&
    ['starting', 'waiting_ready', 'waiting'].includes(state(edge?.target))
}
