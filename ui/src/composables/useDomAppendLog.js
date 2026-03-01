import { nextTick, ref, watch } from 'vue'

function nearBottom(el, threshold = 24) {
  const distance = el.scrollHeight - (el.scrollTop + el.clientHeight)
  return distance <= threshold
}

export function useDomAppendLog(contentRef, options = {}) {
  const logRef = ref(null)
  const autoFollow = ref(true)

  const visibleRef = options.visibleRef || null
  const placeholderRef = options.placeholderRef || null
  const placeholder = options.placeholder || ''

  let renderedText = ''
  let placeholderNode = null
  let contentNode = null

  function clearElement() {
    const el = logRef.value
    if (!el) return
    el.textContent = ''
    placeholderNode = null
    contentNode = null
  }

  function ensureContentNode() {
    const el = logRef.value
    if (!el) return null
    if (placeholderNode) {
      el.removeChild(placeholderNode)
      placeholderNode = null
    }
    if (!contentNode) {
      contentNode = document.createTextNode('')
      el.appendChild(contentNode)
    }
    return contentNode
  }

  function renderPlaceholder() {
    const el = logRef.value
    if (!el) return

    clearElement()

    const text = placeholderRef ? String(placeholderRef.value || '') : String(placeholder || '')
    if (!text) return
    placeholderNode = document.createTextNode(text)
    el.appendChild(placeholderNode)
  }

  function renderFromScratch(text) {
    const node = ensureContentNode()
    if (!node) return

    node.data = text
    renderedText = text
  }

  function appendChunk(chunk) {
    if (!chunk) return
    const node = ensureContentNode()
    if (!node) return

    node.appendData(chunk)
    renderedText += chunk
  }

  function scrollToBottom(force = false) {
    nextTick(() => {
      const el = logRef.value
      if (!el) return
      if (!force && !autoFollow.value) return
      el.scrollTop = el.scrollHeight
      autoFollow.value = true
    })
  }

  function onLogScroll() {
    const el = logRef.value
    if (!el) return
    autoFollow.value = nearBottom(el)
  }

  function syncText(nextText) {
    if (typeof nextText !== 'string') {
      nextText = String(nextText || '')
    }

    if (!nextText) {
      renderedText = ''
      renderPlaceholder()
      return
    }

    if (!renderedText) {
      renderFromScratch(nextText)
      scrollToBottom(false)
      return
    }

    if (nextText.startsWith(renderedText)) {
      appendChunk(nextText.slice(renderedText.length))
      scrollToBottom(false)
      return
    }

    renderFromScratch(nextText)
    scrollToBottom(false)
  }

  function clearLog() {
    renderedText = ''
    renderPlaceholder()
    scrollToBottom(true)
  }

  watch(logRef, (el) => {
    if (!el) return
    syncText(contentRef.value || '')
    scrollToBottom(true)
  })

  watch(contentRef, (value) => {
    syncText(value || '')
  })

  if (visibleRef) {
    watch(visibleRef, (visible) => {
      if (!visible) return
      syncText(contentRef.value || '')
      scrollToBottom(true)
    })
  }

  if (placeholderRef) {
    watch(placeholderRef, () => {
      if (renderedText) return
      renderPlaceholder()
    })
  }

  return {
    logRef,
    onLogScroll,
    autoFollow,
    scrollToBottom,
    clearLog,
  }
}
