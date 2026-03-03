const APPSTORE_API_PREFIX = '/aivuda_app_store'

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

function triggerBrowserDownload(blob, filename) {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(objectUrl), 2000)
}

export function normalizeStoreBaseUrl(baseUrl) {
  return normalizeBaseUrl(baseUrl)
}

export function buildStoreResourceUrl(baseUrl, path) {
  return buildStoreUrl(baseUrl, path)
}

export async function fetchStoreIndex(baseUrl) {
  return requestStoreJson(baseUrl, '/store/index')
}

export async function fetchStoreAppDetail(baseUrl, appId) {
  return requestStoreJson(baseUrl, `/store/apps/${encodeURIComponent(appId)}`)
}

export async function downloadStorePackage(baseUrl, appId, version) {
  const encodedAppId = encodeURIComponent(appId)
  const encodedVersion = encodeURIComponent(version)

  const info = await requestStoreJson(
    baseUrl,
    `/store/apps/${encodedAppId}/versions/${encodedVersion}/download-url`,
  )

  const downloadPath = String(info?.url || '')
  if (!downloadPath) {
    throw new Error('Download URL missing')
  }

  const fileUrl = buildStoreUrl(baseUrl, downloadPath)
  const fileResp = await fetch(fileUrl)
  if (!fileResp.ok) {
    throw new Error(`Download failed: ${fileResp.status}`)
  }

  const blob = await fileResp.blob()
  const filename = `${appId}-${version}.zip`
  triggerBrowserDownload(blob, filename)

  const file = new File([blob], filename, {
    type: blob.type || 'application/zip',
    lastModified: Date.now(),
  })

  return {
    file,
    filename,
    sha256: String(info?.sha256 || ''),
    size: Number(info?.size || 0),
  }
}
