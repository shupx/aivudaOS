import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDomAppendLog } from './useDomAppendLog'

export function useUploadInstallModalView(props, emit) {
  const { t } = useI18n()

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

  function closeByOverlay() {
    emit('close')
  }

  return {
    t,
    logRef,
    onLogScroll,
    shouldShowOutput,
    onFileChange,
    closeByOverlay,
  }
}
