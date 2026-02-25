import { reactive } from 'vue'

const state = reactive({
  username: 'admin',
  password: 'admin123',
  token: localStorage.getItem('token') || '',
  me: null,
  loginError: '',
  busy: false,
  config: null,
  configText: '',
  saveError: '',
  saveOk: '',
  snapshot: null,
  wsStatus: 'disconnected',
  telemetry: null,
  reconnectAttempt: 0,
  appCatalog: [],
  installedApps: [],
  appTaskById: {},
  appConfigById: {},
  appsError: '',
})

let ws = null
let reconnectTimer = null
let pingTimer = null

export function isAuthed() {
  return Boolean(state.token)
}

function authQuery() {
  return `token=${encodeURIComponent(state.token)}`
}

async function apiGet(path) {
  const resp = await fetch(`${path}?${authQuery()}`)
  if (resp.status === 401) {
    logout()
    throw new Error('会话已失效，请重新登录')
  }
  if (!resp.ok) {
    throw new Error(`请求失败: ${resp.status}`)
  }
  return resp.json()
}

async function apiPut(path, body) {
  const resp = await fetch(`${path}?${authQuery()}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (resp.status === 401) {
    logout()
    throw new Error('会话已失效，请重新登录')
  }
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `请求失败: ${resp.status}`)
  }
  return resp.json()
}

async function apiPost(path, body = {}) {
  const resp = await fetch(`${path}?${authQuery()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (resp.status === 401) {
    logout()
    throw new Error('会话已失效，请重新登录')
  }
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `请求失败: ${resp.status}`)
  }
  return resp.json()
}

export async function login() {
  state.loginError = ''
  state.busy = true
  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: state.username, password: state.password }),
    })
    if (!resp.ok) {
      throw new Error('登录失败，账号或密码错误')
    }
    const data = await resp.json()
    state.token = data.access_token
    localStorage.setItem('token', state.token)
    await loadAll()
    openWs(true)
    return true
  } catch (err) {
    state.loginError = err.message
    return false
  } finally {
    state.busy = false
  }
}

export function logout() {
  closeWs()
  state.token = ''
  localStorage.removeItem('token')
  state.me = null
  state.config = null
  state.configText = ''
  state.snapshot = null
  state.telemetry = null
  state.wsStatus = 'disconnected'
  state.reconnectAttempt = 0
  state.appCatalog = []
  state.installedApps = []
  state.appTaskById = {}
  state.appConfigById = {}
  state.appsError = ''
}

export async function loadAll() {
  if (!state.token) return
  state.me = await apiGet('/api/auth/me')
  state.config = await apiGet('/api/config')
  state.configText = JSON.stringify(state.config.data, null, 2)
  state.snapshot = await apiGet('/api/status/snapshot')
  await refreshApps()
}

export async function refreshStatus() {
  if (!state.token) return
  state.snapshot = await apiGet('/api/status/snapshot')
}

export async function refreshApps() {
  if (!state.token) return
  state.appsError = ''
  try {
    await apiPost('/api/apps/repo/sync')
    const [catalogResp, installedResp] = await Promise.all([
      apiGet('/api/apps/catalog'),
      apiGet('/api/apps/installed'),
    ])
    state.appCatalog = catalogResp.items || []
    state.installedApps = installedResp.items || []
  } catch (err) {
    state.appsError = err.message
  }
}

export async function installApp(appId, installRuntime) {
  const result = await apiPost(`/api/apps/${encodeURIComponent(appId)}/install`, {
    install_runtime: Boolean(installRuntime),
  })
  const taskId = result.task_id
  if (taskId) {
    await pollTaskUntilDone(taskId)
  }
  await refreshApps()
}

export async function startApp(appId) {
  await apiPost(`/api/apps/${encodeURIComponent(appId)}/start`)
  await refreshApps()
}

export async function stopApp(appId) {
  await apiPost(`/api/apps/${encodeURIComponent(appId)}/stop`)
  await refreshApps()
}

export async function setAppAutostart(appId, enabled) {
  await apiPost(`/api/apps/${encodeURIComponent(appId)}/autostart`, { enabled: Boolean(enabled) })
  await refreshApps()
}

export async function uninstallApp(appId, purge = false) {
  await apiPost(`/api/apps/${encodeURIComponent(appId)}/uninstall`, { purge: Boolean(purge) })
  await refreshApps()
}

export async function getAppConfig(appId, forceReload = false) {
  if (!forceReload && state.appConfigById[appId]) {
    return state.appConfigById[appId]
  }
  const cfg = await apiGet(`/api/apps/${encodeURIComponent(appId)}/config`)
  state.appConfigById = {
    ...state.appConfigById,
    [appId]: cfg,
  }
  return cfg
}

export async function saveAppConfig(appId, version, data) {
  const resp = await apiPut(`/api/apps/${encodeURIComponent(appId)}/config`, { version, data })
  const cfg = await getAppConfig(appId, true)
  await refreshApps()
  return { version: resp.version, config: cfg }
}

export async function pollTaskUntilDone(taskId) {
  const maxTicks = 120
  for (let i = 0; i < maxTicks; i += 1) {
    const task = await apiGet(`/api/apps/tasks/${encodeURIComponent(taskId)}`)
    state.appTaskById = { ...state.appTaskById, [taskId]: task }
    if (task.status === 'succeeded') return task
    if (task.status === 'failed') {
      throw new Error(task.error || task.message || '安装失败')
    }
    await new Promise((resolve) => setTimeout(resolve, 800))
  }
  throw new Error('安装超时，请稍后刷新查看')
}

export async function saveConfig() {
  state.saveError = ''
  state.saveOk = ''
  try {
    const parsed = JSON.parse(state.configText)
    const result = await apiPut('/api/config', {
      version: state.config.version,
      data: parsed,
    })
    state.saveOk = `保存成功，新版本 ${result.version}`
    state.config = await apiGet('/api/config')
    state.configText = JSON.stringify(state.config.data, null, 2)
    return true
  } catch (err) {
    state.saveError = err.message
    return false
  }
}

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/telemetry?${authQuery()}`
}

function scheduleReconnect() {
  if (!state.token) return
  clearTimeout(reconnectTimer)
  state.reconnectAttempt += 1
  const waitMs = Math.min(30000, 1000 * (2 ** Math.min(state.reconnectAttempt, 5)))
  reconnectTimer = setTimeout(() => openWs(false), waitMs)
}

function closeWs() {
  clearTimeout(reconnectTimer)
  clearInterval(pingTimer)
  reconnectTimer = null
  pingTimer = null
  if (ws) {
    ws.onopen = null
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.close()
    ws = null
  }
}

function openWs(resetAttempt) {
  if (!state.token) return
  closeWs()
  if (resetAttempt) state.reconnectAttempt = 0
  state.wsStatus = 'connecting'

  ws = new WebSocket(wsUrl())
  ws.onopen = () => {
    state.wsStatus = 'connected'
    state.reconnectAttempt = 0
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 5000)
  }

  ws.onmessage = (ev) => {
    try {
      state.telemetry = JSON.parse(ev.data)
    } catch {
      // ignore
    }
  }

  ws.onerror = () => {
    state.wsStatus = 'error'
  }

  ws.onclose = () => {
    state.wsStatus = 'disconnected'
    clearInterval(pingTimer)
    pingTimer = null
    scheduleReconnect()
  }
}

export async function bootstrapSession() {
  if (!state.token) return
  try {
    await loadAll()
    openWs(true)
  } catch {
    logout()
  }
}

export const droneState = state
