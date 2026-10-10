import { computed, onBeforeUnmount, onUpdated, ref, watch } from 'vue'

export function useResizableConfigTable(initialWidths) {
  const columnWidths = ref([...initialWidths])
  const totalTableWidth = computed(() => columnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
  const tableWrapRef = ref(null)
  const resizeLineLefts = ref([])
  // DOM nodes and ref callbacks must not themselves trigger rendering.
  const headers = []
  const headerCallbacks = []
  let frame = null
  let stopColumnResize = null
  let resizeObserver = null

  function queueResizeLineUpdate() {
    if (frame !== null) return
    frame = window.requestAnimationFrame(() => {
      frame = null
      const wrap = tableWrapRef.value
      const next = wrap ? headers.slice(0, -1).map((header) => (
        header ? header.offsetLeft + header.offsetWidth - wrap.scrollLeft : 0
      )) : []
      // onUpdated schedules a measurement, so writing an equal array here
      // would create an endless render -> RAF -> render loop.
      const current = resizeLineLefts.value
      if (next.length !== current.length || next.some((left, index) => left !== current[index])) {
        resizeLineLefts.value = next
      }
    })
  }

  function setHeaderRef(index) {
    if (!headerCallbacks[index]) {
      headerCallbacks[index] = (element) => {
        if (headers[index] === element) return
        headers[index] = element
        queueResizeLineUpdate()
      }
    }
    return headerCallbacks[index]
  }

  function startColumnResize(index, event) {
    event.preventDefault()
    stopColumnResize?.()
    const startX = event.clientX
    const startWidth = Number(columnWidths.value[index] || 0)
    const onPointerMove = (moveEvent) => {
      const width = Math.max(80, startWidth + moveEvent.clientX - startX)
      if (width === columnWidths.value[index]) return
      columnWidths.value = columnWidths.value.map((value, currentIndex) => currentIndex === index ? width : value)
    }
    stopColumnResize = () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', stopColumnResize)
      stopColumnResize = null
    }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', stopColumnResize)
  }

  // Tables appear after async config loading; attach to the actual wrapper.
  watch(tableWrapRef, (wrap, previous) => {
    previous?.removeEventListener('scroll', queueResizeLineUpdate)
    resizeObserver?.disconnect()
    resizeObserver = null
    if (wrap) {
      wrap.addEventListener('scroll', queueResizeLineUpdate, { passive: true })
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(queueResizeLineUpdate)
        resizeObserver.observe(wrap)
      }
    }
    queueResizeLineUpdate()
  }, { flush: 'post' })
  onUpdated(queueResizeLineUpdate)
  onBeforeUnmount(() => {
    stopColumnResize?.()
    resizeObserver?.disconnect()
    tableWrapRef.value?.removeEventListener('scroll', queueResizeLineUpdate)
    if (frame !== null) window.cancelAnimationFrame(frame)
  })

  return { columnWidths, totalTableWidth, tableWrapRef, resizeLineLefts, setHeaderRef, startColumnResize }
}
