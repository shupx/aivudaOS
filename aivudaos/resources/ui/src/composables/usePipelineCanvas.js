import { nextTick, shallowRef } from 'vue'
import {
  GRAPH_SIZE, applyConnect, applyDisconnect, applyGroupOrder, applyMoveToGroup, isEdgeAnimated, toFlowGraph,
} from '../services/core/pipelineGraph.js'

const poolType = 'application/x-aivuda-pipeline-app'

export function usePipelineCanvas({ profile, installed, progress, locked, changed, reject, addFromPool, pauseSave, resumeSave }) {
  const nodes = shallowRef([]), edges = shallowRef([])
  const incident = new Map(), animated = new Set()
  let flow

  function setAnimation(edge, enabled) {
    if (!!edge.animated === enabled) return
    edge.animated = enabled
    const displayed = flow?.findEdge(edge.id)
    if (displayed) displayed.animated = enabled
    if (enabled) animated.add(edge)
    else animated.delete(edge)
  }
  function updateStatus(id) {
    const state = progress.value?.profile === profile.value?.name ? progress.value : null
    for (const edge of incident.get(id) || []) setAnimation(edge, isEdgeAnimated(edge, state))
  }
  function clearAnimation() {
    for (const edge of animated) setAnimation(edge, false)
  }
  function refresh() {
    const graph = toFlowGraph(profile.value, installed.value)
    incident.clear()
    animated.clear()
    const state = progress.value?.profile === profile.value?.name ? progress.value : null
    for (const edge of graph.edges) {
      edge.animated = isEdgeAnimated(edge, state)
      if (edge.animated) animated.add(edge)
      for (const id of [edge.source, edge.target]) {
        if (!incident.has(id)) incident.set(id, [])
        incident.get(id).push(edge)
      }
    }
    nodes.value = graph.nodes
    edges.value = graph.edges
  }
  function fit() {
    nextTick(() => flow?.fitView({ padding: 0.16, maxZoom: 1 }))
  }
  function finish(result) {
    if (result.ok) changed(true)
    else { reject(result.code); refresh() }
  }
  function onConnect(connection) {
    if (!locked.value) finish(applyConnect(profile.value, connection))
  }
  function onNodesChange(changes) {
    flow?.applyNodeChanges(changes.filter(change => change.type !== 'remove'))
  }
  function onEdgesChange(changes) {
    let removed = false
    for (const change of changes) {
      if (change.type !== 'remove' || locked.value) continue
      const edge = flow?.findEdge(change.id)
      if (edge?.data.kind === 'dependency' && applyDisconnect(profile.value, edge).ok) removed = true
    }
    flow?.applyEdgeChanges(changes.filter(change => change.type !== 'remove'))
    if (removed) changed(true)
  }
  const containers = () => nodes.value.filter(n => n.type === 'pipelineGroup')
  function groupAt(point, oldParent) {
    const hits = containers().filter(({ position: p, width, height }) => point.x >= p.x && point.x <= p.x + width &&
      point.y >= p.y && point.y <= p.y + height)
    return hits.find(n => n.id !== oldParent) || hits[0]
  }
  function dragGroup(node) {
    const boxes = containers()
    const center = node.position.x + node.dimensions.width / 2
    const rank = boxes.filter(b => b.id !== node.id && b.position.x + b.width / 2 < center).length
    const from = profile.value.groups.findIndex(g => g.id === node.data.groupId)
    if (rank !== from) {
      const result = applyGroupOrder(profile.value, node.data.groupId, rank)
      if (!result.ok) return finish(result)
    }
    // Freeze default positions before moving a parent so its siblings stay in place.
    const layout = profile.value.layout ??= {}
    for (const box of boxes) if (!layout[box.id]) layout[box.id] = { ...box.position }
    Object.assign(layout[node.id], { x: node.position.x, y: node.position.y })
    changed(true)
  }
  function onDragStop({ node, event }) {
    resumeSave()
    if (locked.value || !node) return refresh()
    if (node.type === 'pipelineGroup') return dragGroup(node)
    const parent = nodes.value.find(n => n.id === node.parentNode)
    if (!parent) return refresh()
    const absolute = { x: parent.position.x + node.position.x, y: parent.position.y + node.position.y }
    const center = { x: absolute.x + node.dimensions.width / 2, y: absolute.y + node.dimensions.height / 2 }
    const pointer = event?.touches?.[0] || event?.changedTouches?.[0] || event
    const point = pointer && flow?.screenToFlowCoordinate({ x: pointer.clientX, y: pointer.clientY })
    const group = (point && groupAt(point, parent.id)) || groupAt(center, parent.id)
    if (!group) return refresh()
    const position = { x: Math.max(0, absolute.x - group.position.x), y: Math.max(GRAPH_SIZE.header, absolute.y - group.position.y) }
    finish(applyMoveToGroup(profile.value, node.data.appId, group.data.groupId, position))
  }
  function onTrayDrag(event, id) {
    if (!event.dataTransfer || locked.value) return
    pauseSave()
    event.dataTransfer.setData(poolType, id)
    event.dataTransfer.effectAllowed = 'move'
  }
  function onDrop(event) {
    const id = event.dataTransfer?.getData(poolType)
    if (!id || !flow || locked.value) return
    resumeSave()
    const point = flow.screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
    const group = groupAt(point)
    const position = group && { x: Math.max(0, point.x - group.position.x), y: Math.max(GRAPH_SIZE.header, point.y - group.position.y) }
    addFromPool(id, group?.data.groupId, position)
  }
  return { nodes, edges, refresh, updateStatus, clearAnimation, fit, onInit(instance) { flow = instance },
    onNodesChange, onEdgesChange, onConnect, onDragStart: pauseSave, onDragStop, onTrayDrag, onDrop,
    onGestureStart: pauseSave, onGestureEnd: resumeSave }
}
