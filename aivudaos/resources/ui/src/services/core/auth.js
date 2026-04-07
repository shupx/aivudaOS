import { request } from './api'
import { appState, clearSession, setToken, setUserSession } from '../../state/appState'

export async function login(username, password) {
  const data = await request('/api/auth/login', {
    method: 'POST',
    body: { username, password },
    auth: false,
  })
  setToken(data.access_token)
  return data
}

export async function fetchMe() {
  const data = await request('/api/auth/me', { auth: true })
  setUserSession(data.username, data.role)
  return data
}

export function isLoggedIn() {
  return Boolean(appState.token)
}

export function logout() {
  clearSession()
}
