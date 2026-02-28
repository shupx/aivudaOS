import { request } from './api'

export async function fetchInstalledApps() {
  const data = await request('/api/apps/installed', { auth: true })
  return data?.items || []
}

export async function fetchAppStatus(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/status`, { auth: true })
}

export async function startApp(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/start`, {
    method: 'POST',
    auth: true,
  })
}

export async function stopApp(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/stop`, {
    method: 'POST',
    auth: true,
  })
}

export async function setAutostart(appId, enabled) {
  return request(`/api/apps/${encodeURIComponent(appId)}/autostart`, {
    method: 'POST',
    body: { enabled: Boolean(enabled) },
    auth: true,
  })
}
