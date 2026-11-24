import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { request } from '../services/core/api'
import { cancelAppOperation, watchPipelineOperation } from '../services/core/apps'
import {
  applyOperationEvent, buildAppListGroups, createStartupPipelineApi, newProgress, pipelineGroupLabel,
} from '../services/core/startupPipeline.js'

export function useAppListGroups({ apps, view, refresh, onAction, t }) {
  const api = createStartupPipelineApi(request)
  const pipelineConfig = shallowRef(null), viewChoice = ref(null)
  const pipelineOperation = ref(null), submitting = ref(false), pipelineCancelPending = ref(false)
  const pipelineConfigLoading = ref(false), configError = ref(''), actionError = ref('')
  const pipelineError = computed(() => actionError.value || configError.value)
  const pipelineConfigReady = computed(() => !!pipelineConfig.value && !configError.value)
  const pipelineBusy = computed(() => !!pipelineOperation.value || submitting.value || pipelineConfigLoading.value)
  const projection = computed(() => buildAppListGroups(apps.value, pipelineConfig.value))
  const appListGroups = computed(() => projection.value.groups)
  const unassignedApps = computed(() => projection.value.unassignedApps)
  const hasPipelineGroups = computed(() => !!appListGroups.value.length)
  const groupedView = computed({
    get: () => hasPipelineGroups.value && (viewChoice.value ?? appListGroups.value.some(g => g.nodeSummaries.size)),
    set: value => { viewChoice.value = value },
  })
  let stream, disposed = false, readId = 0, operationEpoch = 0

  const listSections = computed(() => {
    if (!groupedView.value) return [{ apps: apps.value }]
    const operation = pipelineOperation.value
    let previousEnabled = false
    const sections = appListGroups.value.map((group, index) => {
      let status = ''
      if (operation?.profile === pipelineConfig.value.default_profile) {
        const stage = operation.stages.get(group.id)
        if (operation.group_id === group.id) status = stage || operation.status
        else if (!operation.group_id && (stage === 'starting' || stage === 'stopping')) status = stage
      }
      const showConnector = group.enabled && previousEnabled
      if (group.enabled) previousEnabled = true
      return { group, index, apps: group.apps, showConnector, status }
    })
    if (unassignedApps.value.length) sections.push({ unassigned: true, apps: unassignedApps.value })
    return sections
  })

  function acceptPipelineConfig(config) {
    if (!config || disposed || (pipelineConfig.value && config.version < pipelineConfig.value.version)) return
    configError.value = ''
    pipelineConfig.value = config
  }

  function attach(operation) {
    const id = operation.operation_id
    if (!id) throw new Error(t('pipeline.noOperation'))
    if (pipelineOperation.value?.operation_id === id) return
    operationEpoch++
    stream?.close()
    pipelineCancelPending.value = false
    pipelineOperation.value = newProgress(operation)
    stream = watchPipelineOperation(id, { onEvent(event) {
      const state = pipelineOperation.value
      if (!state || state.operation_id !== id || !applyOperationEvent(state, event) || !state.done) return
      if (state.status === 'failed') actionError.value = event.message || event.error || t('errors.operationFailed')
      stream.close()
      stream = undefined
      pipelineOperation.value = null
      pipelineCancelPending.value = false
      operationEpoch++
      void refresh()
    } })
  }

  async function refreshPipelineConfig() {
    const read = ++readId, epoch = operationEpoch
    pipelineConfigLoading.value = true
    try {
      const data = await api.loadForList()
      if (disposed || read !== readId) return
      acceptPipelineConfig(data.config)
      // A late GET must not replace an operation started or completed while it was in flight.
      if (data.active_operation && epoch === operationEpoch) attach(data.active_operation)
    } catch (error) {
      if (!disposed && read === readId) configError.value = error.message || t('errors.loadFailed')
    } finally {
      if (!disposed && read === readId) pipelineConfigLoading.value = false
    }
  }

  async function execute(action, groupId) {
    if (!pipelineConfigReady.value || !hasPipelineGroups.value || pipelineBusy.value) return
    const profile = pipelineConfig.value.default_profile
    if (groupId != null && !appListGroups.value.some(g => g.id === groupId && g.enabled && g.apps.length)) return
    // The global command resolves the current default under the server's lock.
    const scope = groupId == null ? {} : { profile, group_id: groupId }
    submitting.value = true
    actionError.value = ''
    try {
      const operation = await api[action](scope)
      if (disposed) return
      onAction()
      attach({ profile, ...scope, action, ...operation })
    } catch (error) {
      if (disposed) return
      actionError.value = error.message || t('errors.operationFailed')
      if (error.status === 409) await refreshPipelineConfig()
    } finally {
      if (!disposed) submitting.value = false
    }
  }

  async function cancelPipelineOperation() {
    const id = pipelineOperation.value?.operation_id
    if (!id || pipelineCancelPending.value) return
    pipelineCancelPending.value = true
    try {
      await cancelAppOperation(id)
    } catch (error) {
      if (!disposed && pipelineOperation.value?.operation_id === id) {
        actionError.value = error.message || t('errors.operationFailed')
        pipelineCancelPending.value = false
      }
    }
  }

  onMounted(() => { if (view.value === 'apps') void refreshPipelineConfig() })
  watch(view, tab => { if (tab === 'apps') void refreshPipelineConfig() })
  onUnmounted(() => { disposed = true; stream?.close() })
  return { appListGroups, unassignedApps, hasPipelineGroups, groupedView, listSections,
    pipelineGroupName: group => pipelineGroupLabel(group, t),
    pipelineBusy, pipelineCancelPending, pipelineOperation, pipelineError, pipelineConfigLoading, pipelineConfigReady,
    refreshList: () => Promise.all([refresh(), refreshPipelineConfig()]),
    refreshPipelineConfig, acceptPipelineConfig, cancelPipelineOperation,
    runGroup: id => execute('run', id), restartGroup: id => execute('restart', id), stopGroup: id => execute('stop', id),
    runDefaultPipeline: () => execute('run'), restartDefaultPipeline: () => execute('restart'), stopDefaultPipeline: () => execute('stop'),
  }
}
