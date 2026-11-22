import { ref } from 'vue'

export function useDeferredFieldDrafts(options) {
  const drafts = ref({})
  const buildKey = options?.buildKey || ((item) => String(item ?? ''))
  const getCommittedValue = options?.getCommittedValue || (() => '')
  const commitDraftValue = options?.commitDraftValue || (async () => false)
  const isEqual = options?.isEqual || ((left, right) => left === right)

  function getKey(item) {
    return String(buildKey(item) || '')
  }

  function hasDraft(item) {
    const key = getKey(item)
    return Object.prototype.hasOwnProperty.call(drafts.value, key)
  }

  function getDraftValue(item) {
    const key = getKey(item)
    if (hasDraft(item)) {
      return drafts.value[key]
    }
    return getCommittedValue(item)
  }

  function setDraftValue(item, value) {
    const key = getKey(item)
    drafts.value = {
      ...drafts.value,
      [key]: value,
    }
  }

  function clearDraftValue(item) {
    const key = getKey(item)
    if (!hasDraft(item)) return
    const nextDrafts = { ...drafts.value }
    delete nextDrafts[key]
    drafts.value = nextDrafts
  }

  async function commitDraft(item) {
    const nextValue = getDraftValue(item)
    const currentValue = getCommittedValue(item)
    if (isEqual(nextValue, currentValue)) {
      clearDraftValue(item)
      return true
    }
    const saved = await commitDraftValue(item, nextValue)
    if (saved) {
      clearDraftValue(item)
    }
    return Boolean(saved)
  }

  return {
    getDraftValue,
    setDraftValue,
    clearDraftValue,
    commitDraft,
  }
}
