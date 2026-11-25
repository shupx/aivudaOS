import { computed, ref } from 'vue'

// Each PUT carries the version acknowledged by the preceding PUT. Carry only that
// acknowledgement forward: an older response must never replace the current draft.
export function usePipelineAutosave(config, api, error, onSaved, formatError = e => e.message) {
  const revision = ref(0), acknowledged = ref(0), saveState = ref('idle')
  const dirty = computed(() => acknowledged.value !== revision.value)
  let timer, inFlight, due = 0, paused = false, disposed = false

  function schedule() {
    clearTimeout(timer)
    if (!paused && !disposed && dirty.value && !inFlight && saveState.value === 'pending') {
      timer = setTimeout(write, Math.max(0, due - Date.now()))
    }
  }
  function write() {
    if (inFlight || paused || disposed || !dirty.value || saveState.value === 'conflict') return inFlight
    clearTimeout(timer)
    const sent = revision.value
    saveState.value = 'saving'
    inFlight = api.save(config.value).then(data => {
      config.value.version = data.config.version
      acknowledged.value = sent
      saveState.value = dirty.value ? 'pending' : 'saved'
      if (!dirty.value) onSaved(data)
    }).catch(e => {
      if (e.status === 409) saveState.value = 'conflict'
      else saveState.value = revision.value === sent ? 'error' : 'pending'
      if (saveState.value !== 'pending') error.value = formatError(e)
    }).finally(() => { inFlight = undefined; schedule() })
    return inFlight
  }
  function mark() {
    revision.value++
    due = Date.now() + 500
    if (saveState.value === 'conflict') return
    error.value = ''
    saveState.value = 'pending'
    schedule()
  }
  async function flush() {
    while (dirty.value && !paused && !disposed && !['conflict', 'error'].includes(saveState.value)) await write()
    return !dirty.value
  }
  function retry() {
    if (saveState.value !== 'error') return
    error.value = ''
    return write()
  }
  function reset() {
    clearTimeout(timer)
    acknowledged.value = revision.value
    saveState.value = 'idle'
  }
  return { dirty, saveState, mark, flush, retry, reset,
    pause() { paused = true; clearTimeout(timer) }, resume() { paused = false; schedule() },
    dispose() { disposed = true; clearTimeout(timer) } }
}
