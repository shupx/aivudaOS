import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { markGatewayOnline } from '../state/appState'
import { fetchMe, login } from '../services/core/auth'

export function useLogin() {
  const { t } = useI18n()
  const router = useRouter()
  const busy = ref(false)
  const error = ref('')

  const form = reactive({
    username: 'admin',
    password: 'admin123',
  })

  async function submit() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      await login(form.username, form.password)
      await fetchMe()
      markGatewayOnline(true)
      router.replace('/dashboard')
    } catch (err) {
      markGatewayOnline(false)
      error.value = String(err?.message || err || t('login.failed'))
    } finally {
      busy.value = false
    }
  }

  return {
    form,
    busy,
    error,
    submit,
  }
}
