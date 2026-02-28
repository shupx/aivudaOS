import { request } from './api'

export async function fetchInstalledApps() {
  const data = await request('/api/apps/installed', { auth: true })
  return data?.items || []
}

export async function uploadAppPackage(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/api/apps/upload', {
    method: 'POST',
    body: form,
    auth: true,
  })
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

export async function fetchAppLogs(appId, offset = 0, limit = 65536) {
  return request(
    `/api/apps/${encodeURIComponent(appId)}/logs?offset=${encodeURIComponent(offset)}&limit=${encodeURIComponent(limit)}`,
    { auth: true },
  )
}

export async function fetchAppVersions(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/versions`, { auth: true })
}

export async function switchAppVersion(appId, version, restart = false) {
  return request(`/api/apps/${encodeURIComponent(appId)}/switch-version`, {
    method: 'POST',
    body: { version, restart: Boolean(restart) },
    auth: true,
  })
}

export async function upgradeAppPackage(appId, file) {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/apps/${encodeURIComponent(appId)}/upgrade`, {
    method: 'POST',
    body: form,
    auth: true,
  })
}

export async function uninstallApp(appId, { version = null, purge = false } = {}) {
  return request(`/api/apps/${encodeURIComponent(appId)}/uninstall`, {
    method: 'POST',
    body: {
      version,
      purge: Boolean(purge),
    },
    auth: true,
  })
}
