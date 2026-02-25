import { setUnauthorizedHandler } from './api'
import { isAuthed, login, logout } from './auth'
import { refreshStatus, saveConfig } from './config'
import {
  getAppConfig,
  installApp,
  refreshApps,
  saveAppConfig,
  setAppAutostart,
  startApp,
  stopApp,
  uninstallApp,
} from './apps'
import { bootstrapSession } from './session'
import { robotState } from './state'

setUnauthorizedHandler(logout)

export {
  bootstrapSession,
  robotState,
  getAppConfig,
  installApp,
  isAuthed,
  login,
  logout,
  refreshApps,
  refreshStatus,
  saveAppConfig,
  saveConfig,
  setAppAutostart,
  startApp,
  stopApp,
  uninstallApp,
}
