import { robotState } from './state'

let unauthorizedHandler = () => {}

export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

function authQuery() {
  return `token=${encodeURIComponent(robotState.token)}`
}

async function request(path, options = {}) {
  const resp = await fetch(`${path}?${authQuery()}`, options)
  if (resp.status === 401) {
    unauthorizedHandler()
    throw new Error('会话已失效，请重新登录')
  }
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `请求失败: ${resp.status}`)
  }
  return resp.json()
}

export function apiGet(path) {
  return request(path)
}

export function apiPost(path, body = {}) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiPut(path, body) {
  return request(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
