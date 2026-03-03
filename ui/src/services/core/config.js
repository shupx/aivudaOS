import { request } from './api'

export const DEFAULT_APPSTORE_BASE_URL = 'http://127.0.0.1:9001'

export async function fetchOsConfig() {
  return request('/api/config', { auth: true })
}

export async function updateOsConfig(data, version) {
  return request('/api/config', {
    method: 'PUT',
    body: { data, version },
    auth: true,
  })
}

export function resolveAppStoreBaseUrl(configData) {
  const value = String(configData?.appstore_base_url || '').trim()
  return value || DEFAULT_APPSTORE_BASE_URL
}

export async function saveAppStoreBaseUrl(nextBaseUrl) {
  const cfg = await fetchOsConfig()
  const cleanBaseUrl = String(nextBaseUrl || '').trim().replace(/\/+$/, '')
  const nextData = {
    ...(cfg?.data || {}),
    appstore_base_url: cleanBaseUrl,
  }

  await updateOsConfig(nextData, Number(cfg?.version || 0))
  return nextData.appstore_base_url
}
