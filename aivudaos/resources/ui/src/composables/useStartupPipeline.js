import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { request } from '../services/core/api'
import { cancelAppOperation, fetchAppOperation, subscribeAppOperationEvents } from '../services/core/apps'
import {
  analyzeProfile, applyOperationEvent, applyRos2Template, cloneConfig, createStartupPipelineApi,
  editableConfig, failurePolicies, newGroup, newNode, newProgress, newReadiness, normalizeOrder,
  readinessFields, ros2Stages, unassignedNodes,
} from '../services/core/startupPipeline.js'

export function useStartupPipeline(liveApps) {
  const { t, te } = useI18n()
  const api = createStartupPipelineApi(request)
  const config = ref(null), saved = ref(''), installed = ref([]), selected = ref('')
  const busy = ref(''), error = ref(''), notice = ref(''), validation = ref(null), validatedDraft = ref('')
  const progress = ref(null), connectionLost = ref(false), cancelPending = ref(false)
  const nameDialog = ref(null), nodeDraft = ref(null), destination = ref(null)
  let subscription, pollTimer, disposed = false
  const profile = computed(() => config.value?.profiles.find(p => p.name === selected.value))
  const fingerprint = computed(() => JSON.stringify(config.value))
  const dirty = computed(() => !!config.value && saved.value !== fingerprint.value)
  const checked = computed(() => validatedDraft.value === fingerprint.value ? validation.value : null)
  const appMap = computed(() => {
    const map = new Map(installed.value.map(a => [a.app_id, a]))
    for (const app of liveApps.value) if (map.has(app.app_id)) map.set(app.app_id, { ...map.get(app.app_id), ...app })
    return map
  })
  const pool = computed(() => profile.value ? unassignedNodes(profile.value, installed.value) : [])
  const analysis = computed(() => profile.value ? analyzeProfile(profile.value, installed.value) : { errors: [], preview: [] })
  const conflicts = computed(() => new Set(analysis.value.errors.flatMap(e => e.apps)))
  const preview = computed(() => checked.value?.valid === false ? [] : (checked.value?.preview?.[selected.value] ?? analysis.value.preview))
  const active = computed(() => !!progress.value && !progress.value.done)
  const locked = computed(() => !!busy.value || active.value)
  const canRun = computed(() => !!profile.value && !locked.value && !dirty.value &&
    !analysis.value.errors.length && checked.value?.valid !== false)
  const profileProgress = computed(() => progress.value?.profile === selected.value ? progress.value : null)
  const appName = id => appMap.value.get(id)?.name || id
  function groupName(g) {
    if (!g) return ''
    const original = ros2Stages.find(([id, name]) => id === g.id && name === g.name)
    return original ? t(`pipeline.stages.${g.id}`) : g.name
  }
  function statusName(status) { return te(`pipeline.states.${status}`) ? t(`pipeline.states.${status}`) : status }
  function probeSummary(probe = { type: 'started' }) {
    const label = t(`pipeline.probes.${probe.type}`)
    const detail = { delay: t('pipeline.seconds', { count: probe.delay_sec ?? 1 }),
      tcp: `${probe.host || '127.0.0.1'}:${probe.port ?? ''}`, http: probe.url,
      ros2_node: probe.node_name, ros2_topic: probe.topic, ros2_lifecycle: `${probe.node_name || ''} (${probe.lifecycle_state || 'active'})`,
      command: probe.command }[probe.type]
    return detail ? `${label}: ${detail}` : label
  }
  const options = (values, prefix) => values.map(value => ({ value, label: t(`pipeline.${prefix}.${value}`) }))
  const modes = computed(() => options(['parallel', 'sequential'], 'modes'))
  const policies = computed(() => options(failurePolicies, 'policies'))
  const probeOptions = computed(() => options(Object.keys(readinessFields), 'probes'))
  const profileOptions = computed(() => config.value?.profiles.map(p => ({ value: p.name, label: p.name })) || [])
  const groupOptions = computed(() => profile.value?.groups.map(g => ({ value: g.id, label: groupName(g) })) || [])
  const dependencyOptions = computed(() => (profile.value?.groups || []).flatMap(g => g.items
    .filter(n => nodeDraft.value?.app_id !== n.app_id)
    .map(n => ({ value: n.app_id, label: `${appName(n.app_id)} (${groupName(g)})` }))))

  function rememberValidation(result) {
    validation.value = result
    validatedDraft.value = fingerprint.value
  }
  function receive(data) {
    config.value = editableConfig(data.config)
    saved.value = fingerprint.value
    installed.value = data.installed_apps || data.unassigned_apps || []
    if (!profile.value) selected.value = config.value.default_profile
    rememberValidation(data.validation)
    if (data.active_operation?.operation_id && (!active.value || data.active_operation.operation_id !== progress.value?.operation_id)) {
      attach(data.active_operation)
    }
  }
  async function perform(action, fn) {
    if (busy.value) return
    busy.value = action; error.value = ''; notice.value = ''
    try { await fn() } catch (e) { if (!disposed) error.value = e.message || String(e) }
    finally { if (!disposed) busy.value = '' }
  }
  function load() {
    return perform('load', async () => { const data = await api.load(); if (!disposed) receive(data) })
  }
  function validate() {
    return perform('validate', async () => {
      const result = await api.validate(config.value)
      rememberValidation(result)
      if (result.valid) notice.value = 'valid'
    })
  }
  function save() {
    return perform('save', async () => {
      const result = await api.validate(config.value)
      rememberValidation(result)
      if (!result.valid) return
      const data = await api.save(config.value)
      if (!disposed) { receive(data); notice.value = 'saved' }
    })
  }
  function disconnect() {
    subscription?.close(); subscription = undefined
    clearTimeout(pollTimer); pollTimer = undefined
  }
  function attach(operation) {
    disconnect()
    const id = operation.operation_id
    if (!id) throw new Error(t('pipeline.noOperation'))
    progress.value = newProgress(operation)
    if (config.value.profiles.some(p => p.name === operation.profile)) selected.value = operation.profile
    connectionLost.value = false; cancelPending.value = false
    const current = () => !disposed && progress.value?.operation_id === id && !progress.value.done
    const ingest = event => {
      if (!current()) return
      applyOperationEvent(progress.value, event)
      if (progress.value.done) { disconnect(); connectionLost.value = false; cancelPending.value = false }
    }
    async function poll() {
      try {
        const info = await fetchAppOperation(id)
        if (current()) ingest({ ...info, type: info.done ? 'completed' : 'status' })
      } catch { /* Keep retrying while the browser reconnects. */ }
      if (current() && connectionLost.value) pollTimer = setTimeout(poll, 2000)
      else pollTimer = undefined
    }
    function fallback() {
      if (!current()) return
      connectionLost.value = true
      if (!pollTimer) pollTimer = setTimeout(poll, 300)
    }
    try {
      subscription = subscribeAppOperationEvents(id, {
        onEvent: ingest, onOpen: () => { connectionLost.value = false }, onError: fallback,
      })
    } catch { fallback() }
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

  function reorderGroups(groups) { profile.value.groups = normalizeOrder(groups) }
  function reorderNodes(group, items) { group.items = items; normalizeOrder(profile.value.groups) }
  function moveStage(index, by) {
    const groups = [...profile.value.groups], other = index + by
    if (other < 0 || other >= groups.length) return
    ;[groups[index], groups[other]] = [groups[other], groups[index]]
    reorderGroups(groups)
  }
  function openName(kind, group) { nameDialog.value = { kind, group, value: group ? groupName(group) : '' } }
  const nameValid = computed(() => {
    const d = nameDialog.value, name = d?.value.trim()
    return !!name && !(d.kind === 'addProfile' && config.value.profiles.some(p => p.name === name))
  })
  function submitName() {
    if (!nameValid.value) return
    const { kind, group, value } = nameDialog.value, name = value.trim()
    if (kind === 'removeStage') removeStage(group)
    if (kind === 'renameStage') group.name = name
    if (kind === 'addStage') {
      let n = profile.value.groups.length + 1
      while (profile.value.groups.some(g => g.id === `stage-${n}`)) n++
      reorderGroups([...profile.value.groups, newGroup(`stage-${n}`, name)])
    }
    if (kind === 'addProfile') {
      config.value.profiles.push({ name, on_failure: 'abort', groups: [] }); selected.value = name
    }
    nameDialog.value = null
  }
  function removeStage(group) { reorderGroups(profile.value.groups.filter(g => g.id !== group.id)) }
  function addFromPool(id, groupId) {
    const group = profile.value.groups.find(g => g.id === groupId)
    if (group && pool.value.some(n => n.app_id === id)) reorderNodes(group, [...group.items, newNode(id)])
  }
  const position = ref(1)
  const maxPosition = computed(() => (profile.value?.groups.find(g => g.id === destination.value)?.items || [])
    .filter(n => n.app_id !== nodeDraft.value?.app_id).length + 1)
  function stageActions(group, index) {
    return [
      { key: 'run', label: t('pipeline.runStage'), disabled: !canRun.value || !group.enabled },
      { type: 'divider' },
      { key: 'rename', label: t('pipeline.renameStage') },
      { key: 'earlier', label: t('pipeline.earlier'), disabled: index === 0 },
      { key: 'later', label: t('pipeline.later'), disabled: index === profile.value.groups.length - 1 },
      { key: 'remove', label: t('pipeline.removeStage') },
    ]
  }
  function stageAction(key, group, index) {
    if (key === 'run') return execute(key, group.id)
    if (key === 'rename') return openName('renameStage', group)
    if (key === 'remove') return openName('removeStage', group)
    return moveStage(index, key === 'earlier' ? -1 : 1)
  }
  function editNode(node, group) {
    position.value = group.items.indexOf(node) + 1
    nodeDraft.value = cloneConfig(node)
    nodeDraft.value.readiness = { ...newReadiness(node.readiness?.type || 'started'), ...node.readiness }
    destination.value = group.id
  }
  function changeProbe(type) { nodeDraft.value.readiness = newReadiness(type) }
  function submitNode() {
    const node = nodeDraft.value, groups = profile.value.groups
    const from = groups.find(g => g.items.some(n => n.app_id === node.app_id))
    const to = groups.find(g => g.id === destination.value)
    from.items = from.items.filter(n => n.app_id !== node.app_id)
    if (to) to.items.splice(Math.min(to.items.length, Math.max(0, (position.value || 1) - 1)), 0, node)
    normalizeOrder(groups); nodeDraft.value = null
  }
  const template = () => applyRos2Template(profile.value)
  watch(fingerprint, () => { if (dirty.value) notice.value = '' })
  onMounted(load)
  onUnmounted(() => { disposed = true; disconnect() })
  return { config, profile, selected, dirty, locked, busy, error, notice, pool, analysis, preview,
    checked, conflicts, appMap, appName, groupName, statusName, probeSummary, modes, policies,
    probeOptions, profileOptions, groupOptions, dependencyOptions, destination, nodeDraft, changeProbe,
    editNode, submitNode, nameDialog, nameValid, openName, submitName, removeStage, addFromPool,
    stageActions, stageAction, position, maxPosition, reorderGroups, reorderNodes, template, save, validate, load, execute, cancel,
    active, canRun, progress, profileProgress, connectionLost, cancelPending }
}
