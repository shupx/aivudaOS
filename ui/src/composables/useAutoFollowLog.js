import { nextTick, ref, watch } from 'vue'

function nearBottom(el, threshold = 24) {
  const distance = el.scrollHeight - (el.scrollTop + el.clientHeight)
  return distance <= threshold
}

export function useAutoFollowLog(contentRef, visibleRef = null) {
  const logRef = ref(null)
  const autoFollow = ref(true)

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

  watch(contentRef, () => {
    scrollToBottom(false)
  })

  if (visibleRef) {
    watch(visibleRef, (visible) => {
      if (visible) {
        scrollToBottom(true)
      }
    })
  }

  return {
    logRef,
    onLogScroll,
    autoFollow,
    scrollToBottom,
  }
}
