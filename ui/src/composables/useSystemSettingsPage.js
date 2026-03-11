import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { logout } from '../services/core/auth'
import { fetchSudoNopasswdSetting, triggerRelogin, updateSudoNopasswdSetting } from '../services/core/config'

export function useSystemSettingsPage() {
  const { t } = useI18n()
  const router = useRouter()

  const loading = ref(false)
  const saving = ref(false)
  const reloginPending = ref(false)
  const error = ref('')
  const success = ref('')
  const username = ref('')
  const enabled = ref(false)
  
  // Modal state
  const showPasswordModal = ref(false)
  const sudoPassword = ref('')
  const showSudoPassword = ref(false)
  const pendingToggleValue = ref(false)

  async function load() {
    loading.value = true
    error.value = ''
    success.value = ''
    try {
      const data = await fetchSudoNopasswdSetting()
      username.value = String(data?.username || '')
      enabled.value = Boolean(data?.enabled)
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  function toggleEnabled() {
    if (loading.value || saving.value) return
    pendingToggleValue.value = !enabled.value
    showPasswordModal.value = true
    sudoPassword.value = ''
    showSudoPassword.value = false
  }

  function closePasswordModal() {
    showPasswordModal.value = false
    sudoPassword.value = ''
    showSudoPassword.value = false
    pendingToggleValue.value = false
  }

  async function submitToggle() {
    saving.value = true
    error.value = ''
    success.value = ''
    try {
      if (!sudoPassword.value.trim()) {
        error.value = t('systemSettings.sudoPasswordRequired')
        saving.value = false
        return
      }
      const data = await updateSudoNopasswdSetting(pendingToggleValue.value, sudoPassword.value)
      username.value = String(data?.username || username.value || '')
      enabled.value = Boolean(data?.enabled)
      success.value = t('systemSettings.saveSuccess')
      closePasswordModal()
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.saveFailed'))
    } finally {
      saving.value = false
    }
  }

  async function reloginNow() {
    if (loading.value || saving.value || reloginPending.value) return

    const confirmed = window.confirm(t('systemSettings.reloginWarning'))
    if (!confirmed) return

    reloginPending.value = true
    error.value = ''
    success.value = ''

    try {
      await triggerRelogin()
      success.value = t('systemSettings.reloginTriggered')
      logout()
      router.replace('/login')
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.reloginFailed'))
    } finally {
      reloginPending.value = false
    }
  }

  onMounted(() => {
    load()
  })

  return {
    loading,
    saving,
    reloginPending,
    error,
    success,
    username,
    enabled,
    toggleEnabled,
    showPasswordModal,
    closePasswordModal,
    sudoPassword,
    showSudoPassword,
    submitToggle,
    reloginNow,
    load,
  }
}
