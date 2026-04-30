import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDomAppendLog } from './useDomAppendLog'

export function useUploadInstallModalView(props, emit) {
  const { t } = useI18n()
  const isDragOver = ref(false)

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
