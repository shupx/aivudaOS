import i18n from '../i18n'
import { fetchAppStatus, fetchInstalledApps } from '../services/core/apps'
import { appState, markGatewayOnline, setAppDetail, setApps } from './appState'

let refreshSequence = 0

async function loadDescription(appId) {
  try {
    setAppDetail(appId, await fetchAppStatus(appId))
  } catch {
    // Descriptions are optional. The installed list can still be displayed.
  }
}

export async function refreshInstalledApps({ allDescriptions = false, appId } = {}) {
  const sequence = ++refreshSequence
  const token = appState.token
  const isCurrent = () => sequence === refreshSequence && token === appState.token
  appState.appsLoading = true
  appState.appsError = ''
  try {
    const items = await fetchInstalledApps()
    if (!isCurrent()) return
    if (allDescriptions) {
      const missing = items.filter(item => !appState.appDetailsById[item.app_id])
      await Promise.all(missing.map(item => loadDescription(item.app_id)))
    } else if (appId && !appState.appDetailsById[appId] && items.some(item => item.app_id === appId)) {
      await loadDescription(appId)
    }
    if (!isCurrent()) return
    setApps(items.map(item => ({
      ...item,
      description: appState.appDetailsById[item.app_id]?.manifest?.description || '',
    })))
    markGatewayOnline(true)
  } catch (err) {
    if (!isCurrent()) return
    appState.appsError = String(err?.message || err || i18n.global.t('errors.loadFailed'))
    markGatewayOnline(false)
  } finally {
    if (sequence === refreshSequence) appState.appsLoading = false
  }
}
