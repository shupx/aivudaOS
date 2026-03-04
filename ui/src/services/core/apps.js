import { buildAuthUrl, request } from './api'
import i18n from '../../i18n'

export async function fetchInstalledApps() {
  const data = await request('/api/apps/installed', { auth: true })
  return data?.items || []
}

export async function uploadAppPackage(file, { overwrite = false } = {}) {
  const form = new FormData()
  form.append('file', file)
  const overwriteFlag = overwrite ? '1' : '0'
  return request(`/api/apps/upload?overwrite=${overwriteFlag}`, {
    method: 'POST',
    body: form,
    auth: true,
  })
}

export async function fetchAppStatus(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/status`, { auth: true })
}

export async function startApp(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/start`, {
    method: 'POST',
    auth: true,
  })
}

export async function stopApp(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/stop`, {
    method: 'POST',
    auth: true,
  })
}

export async function setAutostart(appId, enabled) {
  return request(`/api/apps/${encodeURIComponent(appId)}/autostart`, {
    method: 'POST',
    body: { enabled: Boolean(enabled) },
    auth: true,
  })
}

export async function fetchAppLogs(appId, offset = 0, limit = 65536) {
  return request(
    `/api/apps/${encodeURIComponent(appId)}/logs?offset=${encodeURIComponent(offset)}&limit=${encodeURIComponent(limit)}`,
    { auth: true },
  )
}

export async function fetchAppVersions(appId) {
  return request(`/api/apps/${encodeURIComponent(appId)}/versions`, { auth: true })
}

export async function switchAppVersion(appId, version, restart = false) {
  return request(`/api/apps/${encodeURIComponent(appId)}/switch-version`, {
    method: 'POST',
    body: { version, restart: Boolean(restart) },
    auth: true,
  })
}

export async function upgradeAppPackage(appId, file) {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/apps/${encodeURIComponent(appId)}/upgrade`, {
    method: 'POST',
    body: form,
    auth: true,
  })
}

export async function updateAppThisVersion(appId, version) {
  return request(`/api/apps/${encodeURIComponent(appId)}/update_this_version`, {
    method: 'POST',
    body: { version },
    auth: true,
  })
}

export async function uninstallApp(appId, { version = null, purge = false } = {}) {
  return request(`/api/apps/${encodeURIComponent(appId)}/uninstall`, {
    method: 'POST',
    body: {
      version,
      purge: Boolean(purge),
    },
    auth: true,
  })
}

export async function cancelAppOperation(operationId) {
  return request(`/api/apps/operations/${encodeURIComponent(operationId)}/cancel`, {
    method: 'POST',
    auth: true,
  })
}

export async function fetchAppOperation(operationId) {
  return request(`/api/apps/operations/${encodeURIComponent(operationId)}`, {
    auth: true,
  })
}

export function subscribeAppOperationEvents(
  operationId,
  {
    onEvent,
    onError,
    onOpen,
  } = {},
) {
  const url = buildAuthUrl(`/api/apps/operations/${encodeURIComponent(operationId)}/events`)
  const es = new EventSource(url)

  const forward = (event) => {
    try {
      const payload = event?.data ? JSON.parse(event.data) : {}
      if (onEvent) {
        onEvent(payload)
      }
    } catch (err) {
      if (onError) {
        onError(err)
      }
    }
  }

  es.onopen = () => {
    if (onOpen) {
      onOpen()
    }
  }

  es.onerror = () => {
    if (onError) {
      onError(new Error(i18n.global.t('apps.realtimeConnectionError')))
    }
  }

  es.onmessage = forward
  es.addEventListener('status', forward)
  es.addEventListener('log', forward)
  es.addEventListener('error', forward)
  es.addEventListener('completed', forward)
  es.addEventListener('heartbeat', forward)

  return {
    close() {
      es.close()
    },
  }
}

export function openAppOperationInteractiveSocket(
  operationId,
  {
    onMessage,
    onOpen,
    onClose,
    onError,
  } = {},
) {
  const authPath = buildAuthUrl(`/api/apps/operations/${encodeURIComponent(operationId)}/interactive/ws`)
  const absolute = authPath.startsWith('http') ? authPath : `${window.location.origin}${authPath}`
  const wsUrl = absolute.replace(/^http/i, 'ws')
  const socket = new WebSocket(wsUrl)

  socket.onopen = () => {
    if (onOpen) {
      onOpen()
    }
  }

  socket.onmessage = (event) => {
    if (!onMessage) return
    try {
      const payload = event?.data ? JSON.parse(event.data) : {}
      onMessage(payload)
    } catch (err) {
      onError?.(err)
    }
  }

  socket.onerror = () => {
    onError?.(new Error(i18n.global.t('apps.interactiveConnectionError')))
  }

  socket.onclose = () => {
    onClose?.()
  }

  return {
    sendInput(inputText) {
      if (socket.readyState !== WebSocket.OPEN) {
        throw new Error(i18n.global.t('apps.interactiveNotReady'))
      }
      socket.send(JSON.stringify({ type: 'input', data: String(inputText || '') }))
    },
    close() {
      socket.close()
    },
    isOpen() {
      return socket.readyState === WebSocket.OPEN
    },
  }
}
