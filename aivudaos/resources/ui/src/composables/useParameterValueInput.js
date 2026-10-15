import { computed, nextTick, ref, watch } from 'vue'
import { readParameterValueHistory, rememberParameterValue } from '../services/core/parameterValueHistory.js'

export function useParameterValueInput(props, emit) {
  const history = ref([])
  const edited = ref(false)
  let pendingCommit = null
  let lastCommit = null
  let dirty = true

  watch(() => props.historyKey, key => {
    history.value = readParameterValueHistory(key)
    edited.value = false
    lastCommit = null
    dirty = true
  }, { immediate: true })

  const options = computed(() => {
    const query = edited.value ? String(props.value ?? '').toLowerCase() : ''
    return history.value.filter(value => value.toLowerCase().includes(query)).map(value => ({ label: value, value }))
  })

  function onInput(value) {
    edited.value = true
    dirty = true
    emit('update:value', value ?? '')
  }

  function onFocus() {
    edited.value = false
    history.value = readParameterValueHistory(props.historyKey)
  }

  async function commitValue() {
    if (props.disabled) return false
    if (pendingCommit) return pendingCommit
    const key = props.historyKey
    const value = props.value
    if (!dirty && lastCommit?.key === key && lastCommit.value === value) return true
    pendingCommit = (async () => {
      const saved = await props.commit()
      if (saved && key === props.historyKey) {
        history.value = rememberParameterValue(key, value)
        lastCommit = { key, value }
        if (props.value === value) dirty = false
      }
      return saved
    })()
    try {
      return await pendingCommit
    } finally {
      pendingCommit = null
    }
  }

  async function onSelect(value) {
    onInput(value)
    await nextTick()
    await commitValue()
  }

  return { options, onInput, onFocus, onSelect, commitValue }
}
