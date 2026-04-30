import { reactive } from 'vue'
import i18n, { normalizeLocale } from '../i18n'

const TOKEN_KEY = 'aivuda_ui_token'
const LOCALE_KEY = 'aivuda_ui_locale'
const DEFAULT_LOCALE = normalizeLocale(localStorage.getItem(LOCALE_KEY) || 'en-US')

export const appState = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  locale: DEFAULT_LOCALE,
  user: null,
  role: null,
  sidebarCollapsed: true,
  activeMenu: 'apps',
  gatewayOnline: false,
  lastSyncAt: null,
  apps: [],
  appDetailsById: {},
  appsLoading: false,
  appsError: '',
  busyById: {},
})

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

export function setLocale(locale) {
  const normalized = normalizeLocale(locale)
  appState.locale = normalized
  localStorage.setItem(LOCALE_KEY, normalized)
  i18n.global.locale.value = normalized
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
