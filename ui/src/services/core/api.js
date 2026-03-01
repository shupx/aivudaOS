import { appState } from '../../state/appState'
import i18n from '../../i18n'

function buildUrl(path, auth) {
  const raw = path.startsWith('/') ? path : `/${path}`

  if (!auth) return raw
  const token = encodeURIComponent(appState.token || '')
  const separator = raw.includes('?') ? '&' : '?'
  return `${raw}${separator}token=${token}`
}

export function buildAuthUrl(path) {
  return buildUrl(path, true)
}

export async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {}
  const options = { method, headers }

  if (body instanceof FormData) {
    options.body = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  const resp = await fetch(buildUrl(path, auth), options)
  const text = await resp.text()
  let payload = text

  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }

  if (!resp.ok) {
    throw new Error(payload?.detail || i18n.global.t('errors.requestFailed', { status: resp.status }))
  }
  return payload
}
