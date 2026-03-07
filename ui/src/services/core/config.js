import { request } from './api'

// export const DEFAULT_APPSTORE_BASE_URL = 'http://127.0.0.1:9001'
export const DEFAULT_APPSTORE_BASE_URL = 'https://123.56.143.44'
export const APPSTORE_BASE_URL_STORAGE_KEY = 'aivuda_ui_appstore_base_url'

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
  const fromConfig = String(configData?.appstore_base_url || '').trim()
  if (fromConfig) {
    return fromConfig.replace(/\/+$/, '')
  }

  const fromStorage = String(localStorage.getItem(APPSTORE_BASE_URL_STORAGE_KEY) || '').trim()
  const value = fromStorage.replace(/\/+$/, '')
  return value || DEFAULT_APPSTORE_BASE_URL
}

export async function saveAppStoreBaseUrl(nextBaseUrl) {
  const cleanBaseUrl = String(nextBaseUrl || '').trim().replace(/\/+$/, '')
  localStorage.setItem(APPSTORE_BASE_URL_STORAGE_KEY, cleanBaseUrl)
  return cleanBaseUrl
}
