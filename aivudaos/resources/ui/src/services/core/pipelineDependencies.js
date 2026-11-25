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

// Local layout and serial arbitration. The global graph handles cross-group constraints.
// Parallel items of equal depth retain array order; sequential items use ready rank.
export function schedule(group) {
  const items = group.items, serial = group.mode === 'sequential'
  const rank = new Map(items.map((item, i) => [item.app_id, i]))
  const waiting = items.map(() => 0), next = items.map(() => [])
  const depth = serial ? null : items.map(() => 0)
  const sequentialPredecessors = new Map()
  const batches = [], ready = [], ranked = serial ? rankedQueue(items.length) : null
  const enqueue = i => serial ? ranked.add(i) : ready.push(i)
  items.forEach((item, i) => {
    for (const dep of item.depends_on || []) if (rank.has(dep)) {
      next[rank.get(dep)].push(i); waiting[i]++
    }
  })
  waiting.forEach((n, i) => { if (!n) enqueue(i) })
  let visited = 0, cursor = 0, previousApp
  for (let i; (i = serial ? ranked.take() : ready[cursor++]) !== undefined;) {
    visited++
    const item = items[i]
    if (serial && item.enabled !== false) {
      if (previousApp !== undefined) sequentialPredecessors.set(item, previousApp)
      previousApp = item.app_id
      batches.push([item])
    }
    for (const j of next[i]) {
      if (depth) depth[j] = Math.max(depth[j], depth[i] + 1)
      if (--waiting[j] === 0) enqueue(j)
    }
  }
  const unscheduled = []
  items.forEach((item, i) => {
    if (waiting[i] || item.enabled === false) unscheduled.push(item)
    else if (!serial) (batches[depth[i]] ??= []).push(item)
  })
  return { batches: batches.filter(Boolean), unscheduled, sequentialPredecessors, cycle: visited !== items.length }
}

// Validate group gates together with app and sequential edges, including empty groups.
export function graphIssue(groups) {
  const deps = new Map(), enabled = new Map()
  for (const g of groups) {
    const start = 'start:' + g.id, end = 'end:' + g.id
    if (deps.has(start)) return { code: 'duplicate', apps: [g.id] }
    deps.set(start, (g.depends_on || []).map(id => 'end:' + id))
    deps.set(end, [start, ...g.items.map(n => 'app:' + n.app_id)])
    for (const n of g.items) {
      const key = 'app:' + n.app_id
      if (deps.has(key)) return { code: 'duplicate', apps: [n.app_id] }
      enabled.set(key, g.enabled !== false && n.enabled !== false)
      deps.set(key, [start, ...(n.depends_on || []).map(id => 'app:' + id)])
    }
    if (g.mode === 'sequential') {
      for (const [item, previous] of schedule(g).sequentialPredecessors) {
        deps.get('app:' + item.app_id).push('app:' + previous)
      }
    }
  }
  const state = new Map(), stack = []
  const label = key => key.slice(key.indexOf(':') + 1)
  function visit(key) {
    state.set(key, 1)
    stack.push(key)
    for (const dep of deps.get(key)) {
      const issue = code => ({ code, apps: [label(key)], dependency: label(dep) })
      if (!deps.has(dep)) return issue('missing')
      if (enabled.get(key) && enabled.get(dep) === false) return issue('disabled')
      if (state.get(dep) === 1) return { code: 'cycle', apps: stack.slice(stack.indexOf(dep)).map(label) }
      if (!state.has(dep)) {
        const error = visit(dep)
        if (error) return error
      }
    }
    stack.pop()
    state.set(key, 2)
  }
  for (const key of deps.keys()) if (!state.has(key)) {
    const error = visit(key)
    if (error) return error
  }
}
