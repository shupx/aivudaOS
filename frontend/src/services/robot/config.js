import { apiGet, apiPut } from './api'
import { robotState } from './state'

export async function refreshStatus() {
  if (!robotState.token) return
  robotState.snapshot = await apiGet('/api/status/snapshot')
}

export async function saveConfig() {
  robotState.saveError = ''
  robotState.saveOk = ''
  try {
    const parsed = JSON.parse(robotState.configText)
    const result = await apiPut('/api/config', {
      version: robotState.config.version,
      data: parsed,
    })
    robotState.saveOk = `保存成功，新版本 ${result.version}`
    robotState.config = await apiGet('/api/config')
    robotState.configText = JSON.stringify(robotState.config.data, null, 2)
    return true
  } catch (err) {
    robotState.saveError = err.message
    return false
  }
}
