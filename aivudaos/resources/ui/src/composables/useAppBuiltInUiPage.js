import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { buildAppBuiltInUiEntryUrl } from '../services/core/apps'

export function useAppBuiltInUiPage() {
  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const appId = computed(() => String(route.params.appId || ''))
  const reloadTick = ref(0)
  const frameError = ref('')

  const uiSrc = computed(() => {
    if (!appId.value) return ''
    const base = buildAppBuiltInUiEntryUrl(appId.value)
    const separator = base.includes('?') ? '&' : '?'
    return `${base}${separator}_ts=${reloadTick.value}`
  })

  function onFrameLoad() {
    frameError.value = ''
  }

  function onFrameError() {
    frameError.value = t('appBuiltInUi.frameLoadFailed')
  }

  function reloadFrame() {
    frameError.value = ''
    reloadTick.value += 1
  }

  function backToApps() {
    router.push('/dashboard/apps')
  }

  function backToDetail() {
    if (!appId.value) {
      router.push('/dashboard/apps')
      return
    }
    router.push(`/dashboard/apps/${encodeURIComponent(appId.value)}`)
  }

  return {
    appId,
    uiSrc,
    frameError,
    onFrameLoad,
    onFrameError,
    reloadFrame,
    backToApps,
    backToDetail,
  }
}
