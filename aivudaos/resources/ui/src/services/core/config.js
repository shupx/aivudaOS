import { request } from './api'

export const DEFAULT_APPSTORE_BASE_URL = 'https://127.0.0.1:8580'
// export const DEFAULT_APPSTORE_BASE_URL = 'https://39.102.60.150:8580'
export const APPSTORE_BASE_URL_STORAGE_KEY = 'aivuda_ui_appstore_base_url'

export async function fetchSysConfig() {
  return request('/api/config', { auth: true })
}

export async function updateSysConfig(data, version) {
  return request('/api/config', {
    method: 'PUT',
    body: { data, version },
    auth: true,
  })
}

export async function fetchOsConfig() {
  return request('/api/config/os', { auth: true })
}

export async function updateOsConfig(data, version) {
  return request('/api/config/os', {
    method: 'PUT',
    body: { data, version },
    auth: true,
  })
}

export async function fetchSudoNopasswdSetting() {
  return request('/api/config/system/sudo-nopasswd', { auth: true })
}

export async function updateSudoNopasswdSetting(enabled, sudoPassword = '') {
  return request('/api/config/system/sudo-nopasswd', {
    method: 'PUT',
    body: { enabled: Boolean(enabled), sudo_password: String(sudoPassword || '') },
    auth: true,
  })
}

export async function triggerRelogin() {
  return request('/api/config/system/relogin', {
    method: 'POST',
    auth: true,
  })
}

export async function fetchAivudaosServiceStatus() {
  return request('/api/config/system/aivudaos-service', { auth: true })
}

export async function setAivudaosServiceAutostart(enabled) {
  return request('/api/config/system/aivudaos-service/autostart', {
    method: 'POST',
    body: { enabled: Boolean(enabled) },
    auth: true,
  })
}

export async function triggerAivudaosServiceAction(action) {
  return request(`/api/config/system/aivudaos-service/${encodeURIComponent(action)}`, {
    method: 'POST',
    auth: true,
  })
}

export async function fetchAptSourcesList() {
  return request('/api/config/system/apt-sources-list', { auth: true })
}

export async function fetchAptSourcesBackups() {
  return request('/api/config/system/apt-sources-list/backups', { auth: true })
}

export async function updateAptSourcesList(content, sudoPassword = '') {
  return request('/api/config/system/apt-sources-list', {
    method: 'PUT',
    body: {
      content: String(content || ''),
      sudo_password: String(sudoPassword || ''),
    },
    auth: true,
  })
}

export async function restoreAptSourcesBackup(backupId, sudoPassword = '') {
  return request('/api/config/system/apt-sources-list/restore', {
    method: 'POST',
    body: {
      backup_id: String(backupId || ''),
      sudo_password: String(sudoPassword || ''),
    },
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
