import { setUnauthorizedHandler } from './api'
import { isAuthed, login, logout } from './auth'
import { saveConfig } from './config'
import {
  getAppConfig,
  getAppVersions,
  installApp,
  refreshApps,
  saveAppConfig,
  setAppAutostart,
  startApp,
  stopApp,
  switchAppVersion,
  uninstallApp,
} from './apps'
import { bootstrapSession } from './session'
import { robotState } from './state'

setUnauthorizedHandler(logout)

export {
  bootstrapSession,
  robotState,
  getAppConfig,
  getAppVersions,
  installApp,
  isAuthed,
  login,
  logout,
  refreshApps,
  saveAppConfig,
  saveConfig,
  setAppAutostart,
  startApp,
  stopApp,
  switchAppVersion,
  uninstallApp,
}
