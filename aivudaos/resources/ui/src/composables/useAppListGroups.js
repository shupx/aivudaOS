import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { request } from '../services/core/api'
import {
  joinAppListInventory, listStageStatus, prepareAppListGroups, createStartupPipelineApi, pipelineGroupLabel,
} from '../services/core/startupPipeline.js'

export function useAppListGroups({ apps, view, refresh, pipeline, t }) {
  const api = createStartupPipelineApi(request)
  const pipelineConfig = shallowRef(null), viewChoice = ref(null)
  const { active: pipelineOperation, cancelPending: pipelineCancelPending, actionError } = pipeline
  const pipelineConfigLoading = ref(false), configError = ref('')
  const pipelineError = computed(() => actionError.value || configError.value)
  const pipelineConfigReady = computed(() => !!pipelineConfig.value && !configError.value)
  const pipelineLogs = computed(() => pipeline.progress.value?.logs)
  const pipelineBusy = computed(() => !!pipelineOperation.value || pipeline.submitting.value || pipelineConfigLoading.value)
  const preparedGroups = computed(() => prepareAppListGroups(pipelineConfig.value))
  const projection = computed(() => joinAppListInventory(apps.value, preparedGroups.value))
  const appListGroups = computed(() => projection.value.groups)
  const unassignedApps = computed(() => projection.value.unassignedApps)
  const hasPipelineGroups = computed(() => !!appListGroups.value.length)
  const groupedView = computed({
    get: () => hasPipelineGroups.value && (viewChoice.value ?? appListGroups.value.some(g => g.nodeSummaries.size)),
    set: value => { viewChoice.value = value },
  })
  let disposed = false, readId = 0

  const listSections = computed(() => {
    if (!groupedView.value) return [{ apps: apps.value }]
    const operation = pipelineOperation.value
    const names = new Map(appListGroups.value.map(g => [g.id, pipelineGroupLabel(g, t)]))
    let previousEnabled
    const sections = appListGroups.value.map((group, index) => {
      const status = listStageStatus(operation, pipelineConfig.value.default_profile, group.id)
      const showConnector = group.enabled && group.depends_on.includes(previousEnabled)
      if (group.enabled) previousEnabled = group.id
      return { group, index, apps: group.apps, showConnector, status, prerequisites: group.depends_on.map(id => names.get(id) || id) }
    })
    if (unassignedApps.value.length) sections.push({ unassigned: true, apps: unassignedApps.value })
    return sections
  })

  function acceptPipelineConfig(config) {
    if (!config || disposed || (pipelineConfig.value && config.version < pipelineConfig.value.version)) return
    configError.value = ''
    pipelineConfig.value = config
  }

  async function refreshPipelineConfig() {
    const read = ++readId, epoch = pipeline.epoch
    pipelineConfigLoading.value = true
    try {
      const data = await api.loadForList()
      if (disposed || read !== readId) return
      acceptPipelineConfig(data.config)
      // A late GET must not replace an operation started or completed while it was in flight.
      pipeline.attach(data.active_operation, epoch)
    } catch (error) {
      if (!disposed && read === readId) configError.value = error.message || t('errors.loadFailed')
    } finally {
      if (!disposed && read === readId) pipelineConfigLoading.value = false
    }
  }

  async function execute(action, groupId, withDeps = false) {
    if (!pipelineConfigReady.value || !hasPipelineGroups.value || pipelineBusy.value) return
    const profile = pipelineConfig.value.default_profile
    if (groupId != null && !appListGroups.value.some(g => g.id === groupId && g.enabled && g.apps.length)) return
    // The global command resolves the current default under the server's lock.
    const scope = groupId == null ? {} : { profile, group_id: groupId, ...(withDeps ? { with_deps: true } : {}) }
    try {
      await pipeline.execute(action, scope, profile)
    } catch (error) {
      if (disposed) return
      actionError.value = error.message || t('errors.operationFailed')
      if (error.status === 409) await refreshPipelineConfig()
    }
  }

  async function cancelPipelineOperation() {
    try {
      await pipeline.cancel()
    } catch (error) {
      if (!disposed) actionError.value = error.message || t('errors.operationFailed')
    }
  }

  onMounted(() => { if (view.value === 'apps') void refreshPipelineConfig() })
  watch(view, tab => { if (tab === 'apps') void refreshPipelineConfig() })
  onUnmounted(() => { disposed = true })
  return { appListGroups, unassignedApps, hasPipelineGroups, groupedView, listSections,
    pipelineGroupName: group => pipelineGroupLabel(group, t),
    pipelineLogs, pipelineBusy, pipelineCancelPending, pipelineOperation, pipelineError, pipelineConfigLoading, pipelineConfigReady,
    refreshList: () => Promise.all([refresh(), refreshPipelineConfig()]),
    refreshPipelineConfig, acceptPipelineConfig, cancelPipelineOperation,
    runGroup: (id, withDeps) => execute('run', id, withDeps), restartGroup: (id, withDeps) => execute('restart', id, withDeps), stopGroup: id => execute('stop', id),
    runDefaultPipeline: () => execute('run'), restartDefaultPipeline: () => execute('restart'), stopDefaultPipeline: () => execute('stop'),
  }
}
