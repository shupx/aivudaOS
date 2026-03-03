const APPSTORE_API_PREFIX = '/aivuda_app_store'
export const MAX_IN_MEMORY_INSTALL_BYTES = 200 * 1024 * 1024 // 200MB

function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || '').trim().replace(/\/+$/, '')
}

function buildStoreUrl(baseUrl, path) {
  const cleanBase = normalizeBaseUrl(baseUrl)
  const fullPath = path.startsWith('/') ? path : `/${path}`
  if (!cleanBase) {
    return `${APPSTORE_API_PREFIX}${fullPath}`
  }
  if (fullPath.startsWith(APPSTORE_API_PREFIX)) {
    return `${cleanBase}${fullPath}`
  }
  return `${cleanBase}${APPSTORE_API_PREFIX}${fullPath}`
}

function normalizeStorePath(path) {
  const text = String(path || '')
  if (!text) return ''
  if (text.startsWith('/')) return text
  return `/${text}`
}

async function requestStoreJson(baseUrl, path) {
  const resp = await fetch(buildStoreUrl(baseUrl, path))
  const text = await resp.text()
  let payload = text

  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }

  if (!resp.ok) {
    throw new Error(payload?.detail || `Request failed: ${resp.status}`)
  }
  return payload
}

export function triggerBrowserFileDownload(fileUrl, filename) {
  const link = document.createElement('a')
  link.href = fileUrl
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

export function normalizeStoreBaseUrl(baseUrl) {
  return normalizeBaseUrl(baseUrl)
}

export function buildStoreResourceUrl(baseUrl, path) {
  return buildStoreUrl(baseUrl, normalizeStorePath(path))
}

export async function fetchStoreIndex(baseUrl) {
  return requestStoreJson(baseUrl, '/store/index')
}

export async function fetchStoreAppDetail(baseUrl, appId) {
  return requestStoreJson(baseUrl, `/store/apps/${encodeURIComponent(appId)}`)
}

export async function fetchStoreDownloadInfo(baseUrl, appId, version) {
  const encodedAppId = encodeURIComponent(appId)
  const encodedVersion = encodeURIComponent(version)

  return requestStoreJson(
    baseUrl,
    `/store/apps/${encodedAppId}/versions/${encodedVersion}/download-url`,
  )
}

export async function downloadStorePackageByBrowser(baseUrl, appId, version) {
  const info = await fetchStoreDownloadInfo(baseUrl, appId, version)
  const downloadPath = String(info?.url || '')
  if (!downloadPath) {
    throw new Error('Download URL missing')
  }

  const fileUrl = buildStoreResourceUrl(baseUrl, downloadPath)
  const filename = `${appId}-${version}.zip`
  triggerBrowserFileDownload(fileUrl, filename)

  return {
    filename,
  }
}

export async function downloadStorePackageForInstall(baseUrl, appId, version, { onProgress } = {}) {
  const info = await fetchStoreDownloadInfo(baseUrl, appId, version)
  const downloadPath = String(info?.url || '')
  if (!downloadPath) {
    throw new Error('Download URL missing')
  }

  const fileUrl = buildStoreResourceUrl(baseUrl, downloadPath)
  const filename = `${appId}-${version}.zip`
  const size = Number(info?.size || 0)

  // For large files, directly trigger browser download to avoid high memory usage
  if (size > MAX_IN_MEMORY_INSTALL_BYTES) {
    triggerBrowserFileDownload(fileUrl, filename)
    return {
      mode: 'manual',
      filename,
      size,
    }
  }

  // For smaller files, download as blob and trigger download, so that the file can be directly passed to the installer without user needing to find it in local storage
  const resp = await fetch(fileUrl)
  if (!resp.ok) {
    throw new Error(`Download failed: ${resp.status}`)
  }

  if (onProgress) {
    onProgress({ receivedBytes: 0, totalBytes: size > 0 ? size : 0, percent: 0 })
  }

  const headerTotal = Number(resp.headers.get('content-length') || 0)
  const totalBytes = headerTotal > 0 ? headerTotal : (size > 0 ? size : 0)

  let blob
  if (resp.body && typeof resp.body.getReader === 'function') {
    const reader = resp.body.getReader()
    const chunks = []
    let receivedBytes = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (!value) continue

      chunks.push(value)
      receivedBytes += value.byteLength

      if (onProgress) {
        const percent = totalBytes > 0
          ? Math.min(100, Math.round((receivedBytes / totalBytes) * 100))
          : 0
        onProgress({ receivedBytes, totalBytes, percent })
      }
    }

    blob = new Blob(chunks, { type: resp.headers.get('content-type') || 'application/zip' })
  } else {
    blob = await resp.blob()
  }

  if (onProgress) {
    const bytes = blob.size || totalBytes
    onProgress({ receivedBytes: bytes, totalBytes: totalBytes || bytes, percent: 100 })
  }

  const file = new File([blob], filename, {
    type: blob.type || 'application/zip',
    lastModified: Date.now(),
  })

  return {
    mode: 'auto',
    filename,
    size,
    file,
  }
}
