// Numeric version components, SemVer prereleases and build metadata.
// Unknown version formats never produce an update notification.
export function compareVersions(left, right) {
  const parse = (value) => {
    const match = String(value || '').trim().match(/^v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$/)
    return match ? { parts: match[1].split('.').map(BigInt), pre: match[2]?.split('.') || [] } : null
  }
  const a = parse(left)
  const b = parse(right)
  if (!a || !b) return null
  for (let i = 0; i < Math.max(a.parts.length, b.parts.length); i++) {
    const x = a.parts[i] || 0n
    const y = b.parts[i] || 0n
    if (x !== y) return x > y ? 1 : -1
  }
  if (!a.pre.length || !b.pre.length) return a.pre.length === b.pre.length ? 0 : (a.pre.length ? -1 : 1)
  for (let i = 0; i < Math.max(a.pre.length, b.pre.length); i++) {
    const x = a.pre[i]
    const y = b.pre[i]
    if (x === y) continue
    if (x === undefined || y === undefined) return x === undefined ? -1 : 1
    const nx = /^\d+$/.test(x)
    const ny = /^\d+$/.test(y)
    if (nx && ny) {
      if (BigInt(x) === BigInt(y)) continue
      return BigInt(x) > BigInt(y) ? 1 : -1
    }
    if (nx !== ny) return nx ? -1 : 1
    return x > y ? 1 : -1
  }
  return 0
}

export function annotateStoreItems(items, installedApps) {
  const installed = new Map(installedApps.map((app) => [app.app_id, app]))
  return items.map((item) => {
    const app = installed.get(item.app_id)
    const installedVersion = app?.active_version || ''
    const status = !app ? 'notInstalled' : compareVersions(item.version, installedVersion) === 1 ? 'updateAvailable' : 'installed'
    return { ...item, installed_version: installedVersion, installation_status: status }
  })
}
