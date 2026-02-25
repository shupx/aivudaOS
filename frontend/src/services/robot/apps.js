import { apiGet, apiPost, apiPut } from './api'
import { robotState } from './state'

export async function refreshApps() {
  if (!robotState.token) return
  robotState.appsError = ''
  try {
    await apiPost('/api/apps/repo/sync')
    const [catalogResp, installedResp] = await Promise.all([
      apiGet('/api/apps/catalog'),
      apiGet('/api/apps/installed'),
    ])
    robotState.appCatalog = catalogResp.items || []
    robotState.installedApps = installedResp.items || []
  } catch (err) {
    robotState.appsError = err.message
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
  if (!forceReload && robotState.appConfigById[appId]) {
    return robotState.appConfigById[appId]
  }
  const cfg = await apiGet(`/api/apps/${encodeURIComponent(appId)}/config`)
  robotState.appConfigById = {
    ...robotState.appConfigById,
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
    robotState.appTaskById = { ...robotState.appTaskById, [taskId]: task }
    if (task.status === 'succeeded') return task
    if (task.status === 'failed') {
      throw new Error(task.error || task.message || '安装失败')
    }
    await new Promise((resolve) => setTimeout(resolve, 800))
  }
  throw new Error('安装超时，请稍后刷新查看')
}
