import { computed, onUnmounted, ref, shallowRef, watch } from 'vue'
import { request } from '../services/core/api'
import { cancelAppOperation, watchPipelineOperation } from '../services/core/apps'
import { applyOperationEvent, createStartupPipelineApi, newProgress } from '../services/core/startupPipeline.js'

export function usePipelineOperation({ revision, onAction, onFinished, t }) {
  const api = createStartupPipelineApi(request)
  const progress = ref(null), lastEvent = shallowRef(null)
  const active = computed(() => progress.value && !progress.value.done ? progress.value : null)
  const submitting = ref(false), cancelPending = ref(false), connectionLost = ref(false)
  const actionError = ref('')
  let stream, epoch = 0, disposed = false

  function clearFinishedNodeStates() {
    if (progress.value?.done) progress.value.nodes.clear()
  }
  watch(revision, clearFinishedNodeStates)

  function attach(operation, expectedEpoch = epoch) {
    if (!operation || disposed || expectedEpoch !== epoch) return
    const id = operation.operation_id
    if (!id) throw new Error(t('pipeline.noOperation'))
    if (progress.value?.operation_id === id) return
    const attachedEpoch = ++epoch, revisionAtStart = revision.value
    stream?.close()
    cancelPending.value = connectionLost.value = false
    actionError.value = ''
    lastEvent.value = null
    progress.value = newProgress(operation)
    stream = watchPipelineOperation(id, {
      onConnectionChange(connected) { if (epoch === attachedEpoch) connectionLost.value = !connected },
      onEvent(event) {
        const state = progress.value
        if (epoch !== attachedEpoch || !applyOperationEvent(state, event)) return
        lastEvent.value = event
        if (!state.done) return
        epoch++
        stream.close()
        stream = undefined
        cancelPending.value = connectionLost.value = false
        if (revisionAtStart !== revision.value) clearFinishedNodeStates()
        if (state.status === 'failed') actionError.value = event.message || event.error || t('errors.operationFailed')
        void onFinished()
      },
    })
  }

  async function execute(action, scope, profile = scope.profile) {
    if (submitting.value || active.value) return
    submitting.value = true
    actionError.value = ''
    try {
      const operation = await api[action](scope)
      if (!disposed) {
        onAction()
        attach({ profile, ...scope, action, ...operation })
      }
    } finally {
      submitting.value = false
    }
  }

  async function cancel() {
    const operation = active.value
    if (!operation || cancelPending.value) return
    cancelPending.value = true
    try {
      await cancelAppOperation(operation.operation_id)
    } catch (error) {
      if (!disposed && active.value === operation) {
        cancelPending.value = false
        throw error
      }
    }
  }

  onUnmounted(() => { disposed = true; epoch++; stream?.close() })
  return { progress, active, submitting, cancelPending, connectionLost, actionError, lastEvent,
    get epoch() { return epoch }, attach, execute, cancel, clearFinishedNodeStates }
}
