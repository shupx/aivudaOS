import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { appState, markGatewayOnline, setBackendUrl } from '../state/appState'
import { fetchMe, login } from '../services/core/auth'

export function useLogin() {
  const router = useRouter()
  const busy = ref(false)
  const error = ref('')

  const form = reactive({
    backendUrl: appState.backendUrl,
    username: 'admin',
    password: 'admin123',
  })

  async function submit() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      setBackendUrl(form.backendUrl)
      await login(form.username, form.password)
      await fetchMe()
      markGatewayOnline(true)
      router.replace('/dashboard')
    } catch (err) {
      markGatewayOnline(false)
      error.value = String(err?.message || err || '登录失败')
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
