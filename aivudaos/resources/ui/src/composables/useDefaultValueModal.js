import { computed, onBeforeUnmount, ref } from 'vue'
import { copyText } from '../services/core/clipboard'

function formatExpandedValue(value) {
  if (value === null || value === undefined) return { text: '', isJson: false }
  if (typeof value === 'object') return { text: JSON.stringify(value, null, 2), isJson: true }
  const rawText = String(value)
  const trimmed = rawText.trim()
  if (!trimmed) return { text: '', isJson: false }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed)
      if (parsed && typeof parsed === 'object') {
        return { text: JSON.stringify(parsed, null, 2), isJson: true }
      }
    } catch {}
  }
  return { text: rawText, isJson: false }
}

export function useDefaultValueModal() {
  const expandedDefaultValue = ref('')
  const expandedDefaultIsJson = ref(false)
  const defaultValueCopySuccess = ref(false)
  const defaultValueCopyFailed = ref(false)
  const expandedDefaultRows = computed(() => Math.min(24, Math.max(6, expandedDefaultValue.value.split('\n').length)))
  let copyTimer = null
  let generation = 0

  function resetCopyState() {
    generation += 1
    defaultValueCopySuccess.value = false
    defaultValueCopyFailed.value = false
    clearTimeout(copyTimer)
    copyTimer = null
  }

  function openDefaultValueModal(value) {
    resetCopyState()
    const normalized = formatExpandedValue(value)
    expandedDefaultValue.value = normalized.text
    expandedDefaultIsJson.value = normalized.isJson
  }

  function closeDefaultValueModal() {
    resetCopyState()
    expandedDefaultValue.value = ''
    expandedDefaultIsJson.value = false
  }

  async function copyExpandedDefaultValue() {
    const text = expandedDefaultValue.value
    if (!text) return
    resetCopyState()
    const currentGeneration = generation
    try {
      await copyText(text)
      if (currentGeneration !== generation) return
      defaultValueCopySuccess.value = true
      copyTimer = setTimeout(() => {
        defaultValueCopySuccess.value = false
        copyTimer = null
      }, 2000)
    } catch {
      if (currentGeneration === generation) defaultValueCopyFailed.value = true
    }
  }

  onBeforeUnmount(resetCopyState)
  return {
    expandedDefaultValue, expandedDefaultIsJson, expandedDefaultRows,
    defaultValueCopySuccess, defaultValueCopyFailed,
    openDefaultValueModal, closeDefaultValueModal, copyExpandedDefaultValue,
  }
}
