import { robotState, resetStateForLogout } from './state'
import { closeWs, openWs } from './telemetry'
import { loadAll } from './session'

export function isAuthed() {
  return Boolean(robotState.token)
}

export async function login() {
  robotState.loginError = ''
  robotState.busy = true
  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: robotState.username, password: robotState.password }),
    })
    if (!resp.ok) {
      throw new Error('登录失败，账号或密码错误')
    }
    const data = await resp.json()
    robotState.token = data.access_token
    localStorage.setItem('token', robotState.token)
    await loadAll()
    openWs(true)
    return true
  } catch (err) {
    robotState.loginError = err.message
    return false
  } finally {
    robotState.busy = false
  }
}

export function logout() {
  closeWs()
  resetStateForLogout()
}
