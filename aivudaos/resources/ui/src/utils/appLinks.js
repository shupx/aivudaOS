import { buildApiPath } from '../services/core/api'

export function appDetailPath(appId) {
  return `/dashboard/apps/${encodeURIComponent(appId)}`
}

export function appConfigLocation(appId) {
  return { path: '/dashboard/apps/configs', query: { app_id: appId } }
}

export function appIconUrl(appId) {
  return buildApiPath(`/api/apps/${encodeURIComponent(appId)}/icon`)
}
