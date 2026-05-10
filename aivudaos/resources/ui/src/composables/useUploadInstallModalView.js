import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDomAppendLog } from './useDomAppendLog'

export function useUploadInstallModalView(props, emit) {
  const { t } = useI18n()
  const isDragOver = ref(false)
  const fileInputRef = ref(null)
  const interactiveInputRef = ref(null)

  const outputRef = computed(() => props.output)
  const visibleRef = computed(() => props.visible)
  const outputPlaceholder = computed(() => t('apps.waitingOutput'))
  const shouldShowOutput = computed(() => Boolean(props.status || props.output || props.error))

  const {
    logRef,
    onLogScroll,
  } = useDomAppendLog(outputRef, {
    visibleRef,
    placeholderRef: outputPlaceholder,
  })

  function resolveNativeInput(target) {
    if (!target) return null
    if (typeof target.focus === 'function' && target.tagName) {
      return target
    }
    if (typeof target.$el?.querySelector === 'function') {
      return target.$el.querySelector('input, textarea')
    }
    if (typeof target.querySelector === 'function') {
      return target.querySelector('input, textarea')
    }
    return null
  }

  function focusTarget(target) {
    const input = resolveNativeInput(target)
    if (!input || typeof input.focus !== 'function') return false
    input.focus()
    if (typeof input.select === 'function' && !props.interactiveMaskInput) {
      input.select()
    }
    return true
  }

  async function focusPrimaryInput() {
    await nextTick()
    if (props.busy) {
      if (focusTarget(interactiveInputRef.value)) return
    }
    focusTarget(fileInputRef.value)
  }

  watch(
    () => props.visible,
    (visible) => {
      if (!visible) return
      focusPrimaryInput()
    },
  )

  watch(
    () => [props.visible, props.busy],
    ([visible, busy], [prevVisible, prevBusy]) => {
      if (!visible) return
      if (!busy || (prevVisible === visible && prevBusy === busy)) return
      focusPrimaryInput()
    },
  )

  function onFileChange(event) {
    emit('file-change', event?.target?.files || null)
  }

  function emitFiles(fileList) {
    emit('file-change', fileList || null)
  }

  function onDragEnter(event) {
    event?.preventDefault?.()
    isDragOver.value = true
  }

  function onDragOver(event) {
    event?.preventDefault?.()
    isDragOver.value = true
  }

  function onDragLeave(event) {
    event?.preventDefault?.()
    const currentTarget = event?.currentTarget
    const relatedTarget = event?.relatedTarget
    if (currentTarget && relatedTarget instanceof Node && currentTarget.contains(relatedTarget)) {
      return
    }
    isDragOver.value = false
  }

  function onDrop(event) {
    event?.preventDefault?.()
    isDragOver.value = false
    emitFiles(event?.dataTransfer?.files || null)
  }

  function closeByOverlay() {
    emit('close')
  }

  function onInteractiveInput(event) {
    emit('interactive-input', event?.target?.value || '')
  }

  function onInteractiveKeydown(event) {
    if (event?.key !== 'Enter') return
    event.preventDefault()
    emit('interactive-submit')
  }

  function onInteractiveMaskChange(value) {
    emit('interactive-mask-change', Boolean(value))
  }

  return {
    t,
    fileInputRef,
    interactiveInputRef,
    logRef,
    onLogScroll,
    shouldShowOutput,
    isDragOver,
    onFileChange,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
    closeByOverlay,
    onInteractiveInput,
    onInteractiveKeydown,
    onInteractiveMaskChange,
  }
}
