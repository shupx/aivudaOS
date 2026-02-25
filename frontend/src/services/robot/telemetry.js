import { robotState } from './state'

let ws = null
let reconnectTimer = null
let pingTimer = null

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/telemetry?token=${encodeURIComponent(robotState.token)}`
}

function scheduleReconnect() {
  if (!robotState.token) return
  clearTimeout(reconnectTimer)
  robotState.reconnectAttempt += 1
  const waitMs = Math.min(30000, 1000 * (2 ** Math.min(robotState.reconnectAttempt, 5)))
  reconnectTimer = setTimeout(() => openWs(false), waitMs)
}

export function closeWs() {
  clearTimeout(reconnectTimer)
  clearInterval(pingTimer)
  reconnectTimer = null
  pingTimer = null
  if (ws) {
    ws.onopen = null
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.close()
    ws = null
  }
}

export function openWs(resetAttempt) {
  if (!robotState.token) return
  closeWs()
  if (resetAttempt) robotState.reconnectAttempt = 0
  robotState.wsStatus = 'connecting'

  ws = new WebSocket(wsUrl())
  ws.onopen = () => {
    robotState.wsStatus = 'connected'
    robotState.reconnectAttempt = 0
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 5000)
  }

  ws.onmessage = (ev) => {
    try {
      robotState.telemetry = JSON.parse(ev.data)
    } catch {
      // ignore
    }
  }

  ws.onerror = () => {
    robotState.wsStatus = 'error'
  }

  ws.onclose = () => {
    robotState.wsStatus = 'disconnected'
    clearInterval(pingTimer)
    pingTimer = null
    scheduleReconnect()
  }
}
