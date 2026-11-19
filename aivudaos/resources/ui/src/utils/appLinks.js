import { buildApiPath } from '../services/core/api'

export const DEFAULT_APP_ICON_URL = `${import.meta.env.BASE_URL}app-default-icon.png`

export function appDetailPath(appId) {
  return `/dashboard/apps/${encodeURIComponent(appId)}`
}

export function appConfigLocation(appId) {
  return { path: '/dashboard/apps/configs', query: { app_id: appId } }
}

export function appIconUrl(appId) {
  return buildApiPath(`/api/apps/${encodeURIComponent(appId)}/icon`)
}
