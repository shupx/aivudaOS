import { reactive } from 'vue'

const TOKEN_KEY = 'aivuda_ui_token'
const BACKEND_URL_KEY = 'aivuda_ui_backend_url'

export const appState = reactive({
  backendUrl: localStorage.getItem(BACKEND_URL_KEY) || 'http://127.0.0.1:8000',
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: null,
  role: null,
  sidebarCollapsed: false,
  activeMenu: 'apps',
  gatewayOnline: false,
  lastSyncAt: null,
  apps: [],
  appDetailsById: {},
  appsLoading: false,
  appsError: '',
  busyById: {},
})

export function setBackendUrl(url) {
  appState.backendUrl = (url || '').trim()
  localStorage.setItem(BACKEND_URL_KEY, appState.backendUrl)
}

export function setToken(token) {
  appState.token = token || ''
  if (appState.token) {
    localStorage.setItem(TOKEN_KEY, appState.token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function setUserSession(user, role) {
  appState.user = user || null
  appState.role = role || null
}

export function markGatewayOnline(online) {
  appState.gatewayOnline = Boolean(online)
}

export function setApps(items) {
  appState.apps = Array.isArray(items) ? items : []
  appState.lastSyncAt = new Date().toLocaleString()
}

export function patchApp(appId, patch) {
  appState.apps = appState.apps.map((item) => {
    if (item.app_id !== appId) return item
    return { ...item, ...patch }
  })
}

export function setAppDetail(appId, detail) {
  appState.appDetailsById = {
    ...appState.appDetailsById,
    [appId]: detail,
  }
}

export function setBusy(appId, busy) {
  appState.busyById = {
    ...appState.busyById,
    [appId]: Boolean(busy),
  }
}

export function clearSession() {
  setToken('')
  setUserSession(null, null)
  appState.apps = []
  appState.appDetailsById = {}
  appState.appsError = ''
  appState.gatewayOnline = false
  appState.lastSyncAt = null
}
