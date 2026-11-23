import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { request } from '../services/core/api'
import { buildAppIconUrl, cancelAppOperation, fetchAppOperation, subscribeAppOperationEvents } from '../services/core/apps'
import {
  applyOperationEvent, applyRos2Template, cloneConfig, createStartupPipelineApi, editableConfig,
  failurePolicies, newGroup, newProgress, newReadiness, normalizeOrder, profileIssues, readinessFields, ros2Stages,
} from '../services/core/startupPipeline.js'
import { applyAutoLayout, applyGroupOrder, applyMoveToGroup } from '../services/core/pipelineGraph.js'
import { usePipelineCanvas } from './usePipelineCanvas'
import { usePipelineAutosave } from './usePipelineAutosave'

export function useStartupPipeline(liveApps) {
  const { t, te } = useI18n()
  const api = createStartupPipelineApi(request), empty = new Map()
  const config = ref(null), installed = ref([]), selected = ref(''), busy = ref(''), error = ref('')
  const settingsOpen = ref(false), trayOpen = ref(false), nodeDraft = ref(null), destination = ref(''), position = ref(1)
  const progress = ref(null), connectionLost = ref(false), cancelPending = ref(false), valid = ref(false)
  let subscription, pollTimer, disposed = false
  const profile = computed(() => config.value?.profiles.find(p => p.name === selected.value))
  const groupsById = computed(() => new Map(profile.value?.groups.map(g => [g.id, g])))
  const itemsById = computed(() => new Map(profile.value?.groups.flatMap(g => g.items.map(n => [n.app_id, n]))))
  const appMap = computed(() => {
    const map = new Map(installed.value.map(app => [app.app_id, app]))
    for (const app of liveApps.value || []) if (map.has(app.app_id)) map.set(app.app_id, { ...map.get(app.app_id), ...app })
    return map
  })
  const pool = computed(() => [...appMap.value.values()].filter(app => !itemsById.value.has(app.app_id)))
  const active = computed(() => !!progress.value && !progress.value.done)
  const locked = computed(() => !config.value || !!busy.value || active.value)
  const profileProgress = computed(() => selected.value === progress.value?.profile ? progress.value : null)
  const nodeStates = computed(() => profileProgress.value?.nodes || empty)
  const stageStates = computed(() => profileProgress.value?.stages || empty)
  function acceptValidation(data) {
    valid.value = data.validation?.valid !== false
    if (!valid.value) error.value = data.validation.errors.join('\n')
  }
  const autosave = usePipelineAutosave(config, api, error, acceptValidation)
  const canRun = computed(() => !!profile.value && valid.value && !locked.value && !autosave.dirty.value)
  function changed(graph = false) {
    if (graph) canvas.refresh()
    autosave.mark()
  }
  function reject(code) { error.value = t(`pipeline.graphErrors.${code}`); return false }
  const canvas = usePipelineCanvas({ profile, installed, progress, locked, changed, reject,
    addFromPool, pauseSave: autosave.pause, resumeSave: autosave.resume })
  const appName = id => appMap.value.get(id)?.name || id
  const appIcon = id => appMap.value.has(id) ? buildAppIconUrl(appMap.value.get(id)) : ''
  function groupName(group) {
    if (!group) return ''
    return ros2Stages.some(([id, name]) => id === group.id && name === group.name) ? t(`pipeline.stages.${group.id}`) : group.name
  }
  const statusName = state => te(`pipeline.states.${state}`) ? t(`pipeline.states.${state}`) : state
  function readinessBadge(probe) {
    if (probe?.type === 'delay') return t('pipeline.seconds', { count: probe.delay_sec ?? 1 })
    return probe?.type?.startsWith('ros2_') ? t('pipeline.rosBadge') : ''
  }
  const options = (values, prefix) => values.map(value => ({ value, label: t(`pipeline.${prefix}.${value}`) }))
  const policies = computed(() => options(failurePolicies, 'policies'))
  const probeOptions = computed(() => options(Object.keys(readinessFields), 'probes'))
  const profileOptions = computed(() => config.value?.profiles.map(p => ({ value: p.name, label: p.name })) || [])
  const groupOptions = computed(() => (profile.value?.groups || []).map(g => ({ value: g.id, label: groupName(g) })))
  const dependencyOptions = computed(() => {
    const ids = new Set(itemsById.value.keys())
    ids.delete(nodeDraft.value?.app_id)
    // Include invalid saved references so they can be unchecked to repair a draft.
    for (const dep of nodeDraft.value?.depends_on || []) ids.add(dep)
    return [...ids].map(id => ({ value: id, label: appName(id) }))
  })

  async function perform(action, fn) {
    if (busy.value) return
    busy.value = action
    error.value = ''
    try { await fn() } catch (e) { if (!disposed) error.value = e.message }
    finally { if (!disposed) busy.value = '' }
  }
  function load() {
    return perform('load', async () => {
      const data = await api.load()
      if (disposed) return
      config.value = editableConfig(data.config)
      installed.value = data.installed_apps || data.unassigned_apps || []
      if (!profile.value) selected.value = config.value.default_profile
      nodeDraft.value = null
      autosave.reset()
      acceptValidation(data)
      canvas.refresh()
      if (data.active_operation?.operation_id) attach(data.active_operation)
    })
  }
  function selectProfile(name) {
    if (locked.value || !config.value.profiles.some(p => p.name === name)) return
    selected.value = name
    nodeDraft.value = null
    canvas.refresh()
    canvas.fit()
  }
  function addProfile(value) {
    const name = value?.trim()
    if (locked.value || !name || config.value.profiles.some(p => p.name === name)) return false
    config.value.profiles.push({ name, on_failure: 'abort', groups: [] })
    selectProfile(name)
    changed()
    return true
  }
  function makeDefault() { if (!locked.value) { config.value.default_profile = selected.value; changed() } }
  function setPolicy(value) { if (!locked.value && failurePolicies.includes(value)) { profile.value.on_failure = value; changed() } }
  function setTakeover(value) { if (!locked.value) { config.value.takeover_autostart = value; changed() } }
  function check(candidate) {
    const issue = profileIssues(candidate, installed.value)[0]
    if (!issue) return true
    error.value = t(`pipeline.issues.${issue.code}`, { apps: issue.apps.join(', '), dep: issue.dependency })
    return false
  }
  function template() {
    if (locked.value) return
    const candidate = cloneConfig(profile.value)
    applyRos2Template(candidate)
    if (!check(candidate)) return
    profile.value.groups = candidate.groups
    autoLayout()
  }
  function createGroup() {
    let n = profile.value.groups.length + 1
    while (groupsById.value.has(`stage-${n}`)) n++
    const group = newGroup(`stage-${n}`, t('pipeline.newGroup', { n }))
    group.order = profile.value.groups.length
    profile.value.groups.push(group)
    return group
  }
  function addGroup() { if (!locked.value) { createGroup(); changed(true); canvas.fit() } }
  function renameGroup(id, value) {
    const name = value?.trim(), group = groupsById.value.get(id)
    if (locked.value || !name || !group || group.name === name) return
    group.name = name
    changed()
  }
  function toggleMode(id) {
    if (locked.value) return
    const group = groupsById.value.get(id)
    group.mode = group.mode === 'parallel' ? 'sequential' : 'parallel'
    changed(true)
  }
  function setGroupEnabled(id, enabled) {
    if (locked.value) return
    const group = groupsById.value.get(id)
    if (!check({ groups: profile.value.groups.map(g => g === group ? { ...g, enabled } : g) })) return
    group.enabled = enabled
    changed(true)
  }
  function moveGroup(id, delta) {
    if (locked.value) return
    const rank = profile.value.groups.findIndex(g => g.id === id) + delta
    const result = applyGroupOrder(profile.value, id, rank)
    if (!result.ok) return reject(result.code)
    autoLayout()
  }
  function removeItems(draft, ids) {
    for (const group of draft.groups) {
      group.items = group.items.filter(n => !ids.has(n.app_id))
      for (const item of group.items) item.depends_on = item.depends_on.filter(dep => !ids.has(dep))
    }
    for (const id of ids) if (draft.layout) delete draft.layout[`app:${id}`]
    normalizeOrder(draft.groups)
  }
  function removeGroup(id) {
    const group = groupsById.value.get(id)
    if (locked.value || !group) return
    profile.value.groups = profile.value.groups.filter(g => g.id !== id)
    if (profile.value.layout) delete profile.value.layout[`group:${id}`]
    removeItems(profile.value, new Set(group.items.map(n => n.app_id)))
    changed(true)
  }
  function autoLayout() {
    if (locked.value) return
    applyAutoLayout(profile.value)
    changed(true)
    canvas.fit()
  }
  function addFromPool(id, groupId, coordinates) {
    if (locked.value || !appMap.value.has(id) || itemsById.value.has(id)) return
    const target = groupId || profile.value.groups[0]?.id || createGroup().id
    const result = applyMoveToGroup(profile.value, id, target, coordinates)
    if (!result.ok) return reject(result.code)
    changed(true)
    if (!groupId) canvas.fit()
  }
  function editNode(id) {
    if (locked.value || !itemsById.value.has(id)) return
    const group = profile.value.groups.find(g => g.items.some(n => n.app_id === id))
    const draft = cloneConfig(itemsById.value.get(id))
    draft.readiness = { ...newReadiness(draft.readiness.type), ...draft.readiness }
    nodeDraft.value = draft
    destination.value = group.id
    position.value = group.items.findIndex(n => n.app_id === id) + 1
  }
  const maxPosition = computed(() => (groupsById.value.get(destination.value)?.items || []).filter(n => n.app_id !== nodeDraft.value?.app_id).length + 1)
  function setDestination(id) { destination.value = id; position.value = maxPosition.value }
  function changeProbe(type) { if (nodeDraft.value && readinessFields[type]) nodeDraft.value.readiness = newReadiness(type) }
  function closeNode() { nodeDraft.value = null }
  function submitNode() {
    if (locked.value || !nodeDraft.value) return
    const candidate = cloneConfig(profile.value), draft = nodeDraft.value, id = draft.app_id
    if (destination.value) {
      const source = candidate.groups.find(g => g.items.some(n => n.app_id === id))
      source.items.splice(source.items.findIndex(n => n.app_id === id), 1, cloneConfig(draft))
      const move = applyMoveToGroup(candidate, id, destination.value, null, Number(position.value) - 1)
      if (!move.ok) return reject(move.code)
    } else removeItems(candidate, new Set([id]))
    if (!check(candidate)) return
    config.value.profiles.splice(config.value.profiles.indexOf(profile.value), 1, candidate)
    closeNode()
    changed(true)
  }

  function disconnect() { subscription?.close(); subscription = undefined; clearTimeout(pollTimer); pollTimer = undefined }
  function attach(operation) {
    disconnect()
    const id = operation.operation_id
    if (!id) throw new Error(t('pipeline.noOperation'))
    if (config.value.profiles.some(p => p.name === operation.profile) && selected.value !== operation.profile) {
      selected.value = operation.profile
      nodeDraft.value = null
      canvas.refresh()
      canvas.fit()
    }
    canvas.clearAnimation()
    progress.value = newProgress(operation)
    connectionLost.value = false
    cancelPending.value = false
    const current = () => !disposed && progress.value?.operation_id === id && !progress.value.done
    function ingest(event) {
      if (!current()) return
      applyOperationEvent(progress.value, event)
      if (event.type === 'pipeline_node') canvas.updateStatus(`app:${event.app_id}`)
      if (event.type === 'pipeline_stage') canvas.updateStatus(`group:${event.group_id}`)
      if (progress.value.done) {
        disconnect()
        canvas.clearAnimation()
        connectionLost.value = cancelPending.value = false
      }
    }
    async function poll() {
      try {
        const info = await fetchAppOperation(id)
        if (current()) ingest({ ...info, type: info.done ? 'completed' : 'status' })
      } catch { /* EventSource retries independently. */ }
      pollTimer = current() && connectionLost.value ? setTimeout(poll, 2000) : undefined
    }
    function fallback() {
      if (!current()) return
      connectionLost.value = true
      if (!pollTimer) pollTimer = setTimeout(poll, 300)
    }
    try { subscription = subscribeAppOperationEvents(id, { onEvent: ingest, onOpen: () => { connectionLost.value = false }, onError: fallback }) }
    catch { fallback() }
  }
  function execute(action, groupId) {
    if (!canRun.value) return
    const scope = { profile: selected.value, ...(groupId ? { group_id: groupId } : {}) }
    return perform(action, async () => {
      const operation = await api[action](scope)
      if (!disposed) attach({ ...scope, ...operation, action })
    })
  }
  function cancel() {
    if (!active.value || cancelPending.value) return
    return perform('cancel', async () => {
      cancelPending.value = true
      try { await cancelAppOperation(progress.value.operation_id) }
      catch (e) { cancelPending.value = false; throw e }
    })
  }
  onMounted(load)
  onBeforeRouteLeave(() => autosave.flush())
  onUnmounted(() => {
    disposed = true
    disconnect()
    autosave.flush().finally(autosave.dispose)
  })
  return { config, profile, selected, groupsById, itemsById, appMap, pool, busy, error, active, locked, canRun,
    saveState: autosave.saveState, dirty: autosave.dirty, retrySave: autosave.retry, settingsOpen, trayOpen,
    nodeDraft, destination, position, maxPosition, dependencyOptions, groupOptions, profileOptions, policies, probeOptions,
    progress, profileProgress, nodeStates, stageStates, cancelPending, connectionLost, groupName, appName, appIcon, statusName, readinessBadge,
    selectProfile, addProfile, makeDefault, setPolicy, setTakeover, template, addGroup, renameGroup, toggleMode, setGroupEnabled,
    removeGroup, moveGroup, autoLayout, addFromPool, editNode, closeNode, setDestination, changeProbe, submitNode, execute, cancel, load,
    ...canvas }
}
