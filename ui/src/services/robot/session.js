import { apiGet } from './api'
import { logout } from './auth'
import { refreshApps } from './apps'
import { robotState } from './state'

export async function loadAll() {
  if (!robotState.token) return
  robotState.me = await apiGet('/api/auth/me')
  robotState.config = await apiGet('/api/config')
  robotState.configText = JSON.stringify(robotState.config.data, null, 2)
  await refreshApps()
}

export async function bootstrapSession() {
  if (!robotState.token) return
  try {
    await loadAll()
  } catch {
    logout()
  }
}
