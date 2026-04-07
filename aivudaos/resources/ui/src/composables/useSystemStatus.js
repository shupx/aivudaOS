import { computed } from 'vue'
import { appState } from '../state/appState'

export function useSystemStatus() {
  const user = computed(() => appState.user)
  const role = computed(() => appState.role)
  const gatewayOnline = computed(() => appState.gatewayOnline)
  const totalApps = computed(() => appState.apps.length)
  const runningApps = computed(() => appState.apps.filter((item) => Boolean(item.running)).length)
  const autostartApps = computed(() => appState.apps.filter((item) => Boolean(item.autostart)).length)
  const lastSyncAt = computed(() => appState.lastSyncAt)

  return {
    user,
    role,
    gatewayOnline,
    totalApps,
    runningApps,
    autostartApps,
    lastSyncAt,
  }
}
